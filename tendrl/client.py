import json
import os
import platform
from queue import Queue, Empty, Full as QueueFull
import socket
import threading
import time
from typing import Callable, List, Union
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

from tendrl.utils import make_message
from tendrl.utils.utils import get_system_metrics, calculate_dynamic_batch_size, get_system_resources
from tendrl.models import Message, HeartbeatMessage, HeartbeatData
from .storage import SQLiteStorage

VERSION = "0.1.7"

class APIException(Exception):
    """Exception raised for API-related errors."""

    pass


class Client:
    """Tendrl client for data collection with offline storage and dynamic batching."""

    __slots__ = (
        "sock",
        "queue",
        "sender_thread",
        "callback",
        "mode",
        "client",
        "_stop_event",
        "check_msg_rate",
        "check_msg_limit",
        "_run_lock",
        "_last_msg_check",
        "debug",
        "_db",
        "_db_lock",
        "db_filepath",
        "target_cpu_percent",
        "target_mem_percent",
        "min_batch_size",
        "max_batch_size",
        "min_batch_interval",
        "max_batch_interval",
        "storage",
        "_last_cleanup",
        "max_queue_size",
        "_connection_state",
        "_last_connection_check",
        "_is_windows",
        "headless",
        "send_heartbeat",
        "heartbeat_interval",
        "_last_heartbeat",
    )

    def __init__(
        self,
        mode: str = "api",
        api_key: str = None,
        check_msg_rate: float = 3,
        check_msg_limit: int = 1,
        debug: bool = False,
        target_cpu_percent: float = 65.0,
        target_mem_percent: float = 75.0,
        min_batch_size: int = 10,
        max_batch_size: int = 100,
        min_batch_interval: float = 0.1,
        max_batch_interval: float = 1.0,
        offline_storage: bool = False,
        db_path: str = "tendrl_offline.db",
        callback: Callable = None,
        max_queue_size: int = 1000,
        headless: bool = False,
        send_heartbeat: bool = True,
        heartbeat_interval: int = 30,
    ):
        """Initialize Tendrl client with optional offline storage and dynamic batching.

        Args:
            mode: Operating mode ('api' or 'agent') (default: 'api')
            api_key: API key for authentication (or use TENDRL_KEY env var)
            check_msg_rate: Message check frequency in seconds (default: every 3 seconds)
            check_msg_limit: Maximum number of messages to retrieve (default: 1)
            debug: Enable debug logging (default: False)
            target_cpu_percent: Target CPU usage for batch sizing (default: 65.0)
            target_mem_percent: Target memory usage for batch sizing (default: 75.0)
            min_batch_size: Minimum messages per batch (default: 10)
            max_batch_size: Maximum messages per batch (default: 100)
            min_batch_interval: Minimum seconds between batches (default: 0.1)
            max_batch_interval: Maximum seconds between batches (default: 1.0)
            offline_storage: Enable message persistence (default: False)
            db_path: Custom path for storage database (default: tendrl_offline.db)
            callback: Optional callback for message handling (default: None)
            max_queue_size: Maximum size of the message queue (default: 1000)
            headless: Pure SDK mode - no background processing (default: False)
            send_heartbeat: Enable automatic heartbeat messages (default: True)
            heartbeat_interval: Interval between heartbeats in seconds (default: 30)
        """
        self.callback = None
        if callback:
            if not callable(callback):
                raise TypeError("callback must be a callable function accepting dict")
            self.callback = callback

        self.mode = mode if mode == "api" else "agent"
        self.check_msg_rate = check_msg_rate
        self.check_msg_limit = check_msg_limit
        self.debug = debug
        self.queue = Queue(maxsize=max_queue_size)
        self._run_lock = threading.Lock()
        self._last_msg_check = time.time() * 1000
        self._stop_event = threading.Event()
        self._db_lock = threading.Lock()
        self.db_filepath = db_path
        self.target_cpu_percent = target_cpu_percent
        self.target_mem_percent = target_mem_percent
        self.min_batch_size = min_batch_size
        self.max_batch_size = max_batch_size
        self.min_batch_interval = min_batch_interval
        self.max_batch_interval = max_batch_interval
        self.headless = headless
        self.sender_thread = None if headless else threading.Thread(target=self._run_sender, daemon=True)
        self._is_windows = platform.system() == 'Windows'

        if self.mode == "agent":
            # Use AF_UNIX on all platforms
            self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            if self.debug:
                if self._is_windows:
                    print("Agent mode: Using AF_UNIX on Windows (requires Windows 10 1803+)")
                else:
                    print("Agent mode: Using AF_UNIX socket")
        elif self.mode == "api":
            api_key = api_key or os.getenv("TENDRL_KEY")
            if not api_key:
                raise APIException("No api_key provided and TENDRL_KEY env var not set")
            
            self.client = httpx.Client(
                http2=True,
                base_url="https://app.tendrl.com/api",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "User-Agent": f"tendrl-python-sdk/{VERSION}"
                }
            )

        self._last_cleanup = time.time() * 1000
        self.storage = None
        if offline_storage:
            if self.debug:
                print(
                    f"Initializing offline storage at {db_path or 'tendrl_storage.db'}"
                )
            self.storage = SQLiteStorage(db_path or "tendrl_storage.db")

        self._connection_state = True  # Assume connected initially
        self._last_connection_check = time.time() * 1000
        
        # Heartbeat configuration
        self.send_heartbeat = send_heartbeat and not headless  # Disable in headless mode
        self.heartbeat_interval = heartbeat_interval
        self._last_heartbeat = 0

    def _connect_to_agent(self):
        """Establish connection to the agent using AF_UNIX socket."""
        socket_path = self._get_socket_path()

        try:
            self.sock.connect(socket_path)
            if self.debug:
                print(f"Connected to agent via AF_UNIX socket at {socket_path}")
        except socket.error as e:
            if self._is_windows:
                raise ConnectionError(f"Failed to connect to Tendrl agent: {e}\n"
                                    "Ensure Windows 10 1803+ and AF_UNIX support is enabled.\n"
                                    "Check with: sc query afunix")
            else:
                raise ConnectionError(f"Failed to connect to Tendrl agent: {e}")

    def _get_socket_path(self):
        """Get platform-appropriate socket path."""
        if self._is_windows:
            # Windows: Standard ProgramData location
            return "C:\\ProgramData\\tendrl\\tendrl_agent.sock"
        else:
            # Unix/Linux: Standard /var/lib location
            return "/var/lib/tendrl/tendrl_agent.sock"

    def check_msg(self) -> None:
        """Check for messages from the server.

        Args:
            limit: Maximum number of messages to retrieve
        """
        if self._stop_event.is_set():
            return
        try:
            if self.mode == "agent":
                payload = json.dumps({"msg_type": "msg_check"}).encode("utf-8")
                self.sock.sendall(payload)
                response = self.sock.recv(1024).decode() # increase
                if response == "204":
                    return
            else:
                try:
                    response = self.client.get(
                        url=f"/entities/check_messages?limit={self.check_msg_limit}"
                    )

                    if response.status_code == 204:
                        # No messages available
                        return
                    
                    if response.status_code != 200:
                        # Log error for non-200 status codes
                        if self.debug:
                            print(f"❌ check_messages failed with status {response.status_code}: {response.text}")
                        return
                    
                    # Parse response JSON
                    try:
                        response_data = response.json()
                    except json.JSONDecodeError:
                        if self.debug:
                            print("❌ Failed to decode JSON from check_messages response")
                        return
                    
                    # Extract messages from response
                    messages = response_data.get("messages")
                    if not messages:
                        # No messages in response (shouldn't happen with 200, but handle gracefully)
                        return
                    
                    # Ensure messages is a list
                    if not isinstance(messages, list):
                        if self.debug:
                            print(f"❌ Expected messages to be a list, got {type(messages)}")
                        return
                    
                    # If no callback is set, log a warning in debug mode
                    if not self.callback:
                        if self.debug:
                            print(f"⚠️ Received {len(messages)} message(s) but no callback is set")
                        return
                    
                    # Process messages through callback
                    # The API returns CheckMessage format: {data, tags, source, timestamp}
                    # We need to transform it to match the expected Message format: {msg_type, data, context: {tags}, source, timestamp}
                    for message in messages:
                        if not isinstance(message, dict):
                            if self.debug:
                                print(f"⚠️ Skipping invalid message format: {type(message)}")
                            continue
                        
                        # Transform CheckMessage to Message format
                        # 1. Add msg_type if missing (default to "command" for incoming messages)
                        if "msg_type" not in message:
                            message["msg_type"] = "command"
                        
                        # 2. Move tags to context.tags if tags exist at top level
                        if "tags" in message:
                            tags = message.pop("tags")
                            # Only add context if tags is not empty
                            if tags:
                                if "context" not in message:
                                    message["context"] = {}
                                if not isinstance(message["context"], dict):
                                    message["context"] = {}
                                message["context"]["tags"] = tags
                        
                        try:
                            self.callback(message)
                        except Exception as e:
                            if self.debug:
                                print(f"❌ Error in callback processing message: {e}")
                            # Continue processing other messages even if one fails
                            
                except httpx.HTTPError as error:
                    if self.debug:
                        print(f"❌ HTTP error checking messages: {error}")
                    return None
        except json.JSONDecodeError:
            if self.debug:
                print("❌ Failed to decode JSON from response.")
        except socket.error as e:
            if self.debug:
                print(f"❌ Socket error: {e}")

    def publish(
        self, msg: Union[dict, str], tags=None, entity="",
        wait_response=False, timeout=5) -> str:
        if not isinstance(msg, (dict, str)):
            raise ValueError(f"Invalid type: {type(msg)}")

        message = make_message(
            msg,
            "publish",
            tags=tags,
            entity=entity,
            wait_response=wait_response,
        )

        if wait_response or self.headless:
            return self._publish_message(message, timeout=timeout)

        self.queue.put(message)
        return ""

    def tether(
        self,
        tags: List[str] = None,
        write_offline: bool = False,
        db_ttl: int = 3600,
    ) -> None:
        """
        Decorator for data collection with optional offline storage.

        Args:
            tags: List of tags for the message
            write_offline: Enable offline storage for this tether
            db_ttl: Time-to-live in seconds for stored messages
        """

        def wrapper(func):
            def wrapped_function(*args, **kwargs):
                data = func(*args, **kwargs)
                if self.headless:
                    # In headless mode, publish directly
                    message = make_message(data, "publish", tags=tags)
                    self._publish_message(message)
                else:
                    try:
                        self.queue.put(make_message(data, "publish", tags=tags))
                    except QueueFull:
                        if write_offline and self.storage:
                            if self.debug:
                                print(f"Queue full, storing message with TTL {db_ttl}s")
                            self.storage.store(
                                str(time.time()), data, tags=tags, ttl=db_ttl
                            )
                return data

            return wrapped_function

        return wrapper

    def start(self):
        """Start the message sender thread."""
        if not self.headless and self.sender_thread:
            self.sender_thread.start()
        
        # Update entity status to online
        if self.mode == "api":
            self._update_entity_status(online=True)

    def stop(self):
        """Stop the client and cleanup resources."""
        # Update entity status to offline before stopping
        if self.mode == "api":
            self._update_entity_status(online=False)
        
        if not self.headless and self.sender_thread:
            self._stop_event.set()
            self.queue.put(None)  # Send stop signal to sender thread
            self.sender_thread.join()
        if self.mode == "agent":
            self.sock.close()
        else:
            self.client.close()
        if self.storage:
            self.storage.close()

    def _publish_message(self, message, timeout: int = 5):
        """Publish a single message to the server.

        Args:
            message: Message to publish (Message model or dict)
            timeout: Request timeout in seconds
        """
        # Convert Message model to dict for JSON serialization
        if isinstance(message, Message):
            message_dict = message.model_dump()
        else:
            message_dict = message
        
        try:
            if self.mode == "agent":
                original_timeout = self.sock.gettimeout() if timeout else None

                try:
                    self.sock.sendall(json.dumps(message_dict).encode("utf-8"))
                    if message_dict.get("context", {}).get("wait"):
                        msg_id = json.loads(self.sock.recv(1024).decode()).get("id")
                        return msg_id
                except socket.timeout as err:
                    return str(f"error: {err.errno}")
                except socket.error as e:
                    if e.errno == 32:  # Broken pipe
                        raise ConnectionError(
                            "Failed to connect to Tendrl Server"
                        ) from e

                if original_timeout:
                    self.sock.settimeout(original_timeout)

            else:  # HTTP Client Mode
                response = self.client.post(
                    url="/entities/message",
                    json=message_dict,
                    timeout=timeout,
                )

                if response.status_code == 200 and response.content:
                    # API returns {"code": 200, "content": id}
                    return response.json()
                elif response.status_code != 200:
                    if self.debug:
                        print(f"Message publish failed with status {response.status_code}: {response.text}")
                    return None
        except httpx.HTTPError as error:
            return error
        except socket.error as e:
            if self.debug:
                print(f"Agent Socket Error: {e}")

    def _publish_messages(self, messages: List[Union[dict, Message]]) -> None:
        """Publish a batch of messages to the server.

        Args:
            messages: List of messages to publish (Message models or dicts)
        """
        if not messages:
            return
            
        # Check if any messages require individual handling (wait_response=True)
        individual_messages = []
        batch_messages = []
        
        for message in messages:
            # Convert Message to dict for checking
            msg_dict = message.model_dump() if isinstance(message, Message) else message
            if msg_dict.get("context", {}).get("wait"):
                individual_messages.append(message)
            else:
                batch_messages.append(message)
        
        # Send batch messages using the batch endpoint
        if batch_messages:
            try:
                if self.mode == "agent":
                    # For agent mode, send individual messages (no batch support in socket protocol)
                    for message in batch_messages:
                        self._publish_message(message)
                else:
                    # Convert Message models to dicts for JSON serialization
                    batch_dicts = [
                        msg.model_dump() if isinstance(msg, Message) else msg
                        for msg in batch_messages
                    ]
                    # Use batch endpoint for HTTP API
                    # API expects array directly, not wrapped in "messages" key
                    response = self.client.post(
                        url="/entities/messages",  # Batch endpoint
                        json=batch_dicts,  # Send array directly
                        timeout=30,  # Longer timeout for batch requests
                    )
                    if self.debug and response.status_code != 200:
                        print(f"Batch request failed with status {response.status_code}")
                    # API returns {"code": 200, "content": messageIDs}
                    # Response is handled silently for batch operations
            except Exception as e:
                if self.debug:
                    print(f"Batch request failed: {e}, falling back to individual requests")
                # Fallback to individual requests
                for message in batch_messages:
                    self._publish_message(message)
        
        # Send individual messages that require wait_response
        for message in individual_messages:
            self._publish_message(message)

    def _run_sender(self) -> None:
        """Process messages from queue in dynamic batches."""
        batch_interval = self.min_batch_interval

        while not self._stop_event.is_set():
            if not self._run_lock.locked():
                with self._run_lock:
                    start_time = time.time() * 1000

                    # Check connection state periodically (every 30 seconds)
                    current_time = time.time() * 1000
                    if current_time >= (self._last_connection_check + 30000):
                        previous_state = self._connection_state
                        self._connection_state = self.check_connection_state()
                        self._last_connection_check = current_time

                        # If connection was restored, process offline messages
                        if not previous_state and self._connection_state:
                            if self.debug:
                                print("Connection restored, processing offline messages")
                            self.process_offline_messages()

                    batch = []

                    # Get system metrics and calculate dynamic batch size
                    metrics = get_system_metrics(self.queue.qsize(), self.queue.maxsize)
                    dynamic_batch_size = calculate_dynamic_batch_size(
                        metrics,
                        self.target_cpu_percent,
                        self.target_mem_percent,
                        self.min_batch_size,
                        self.max_batch_size
                    )

                    # Adjust batch interval based on queue load
                    batch_interval = self.max_batch_interval * (
                        1 - metrics.queue_load / 100
                    )
                    batch_interval = max(self.min_batch_interval, batch_interval)

                    # Collect up to batch_size messages from the queue
                    while len(batch) < dynamic_batch_size and not self.queue.empty():
                        try:
                            msg = self.queue.get(timeout=batch_interval)
                            batch.append(msg)
                            self.queue.task_done()
                        except Empty:
                            break

                    if batch:
                        if self.debug:
                            print(
                                f"Queue load: {metrics.queue_load:.1f}%, CPU: {metrics.cpu_usage:.1f}%, "
                                f"Memory: {metrics.memory_usage:.1f}%, Batch size: {len(batch)}"
                            )

                        # Only send if we have connection
                        if self._connection_state:
                            self._publish_messages(batch)
                        else:
                            # Store messages offline if storage is enabled
                            if self.storage:
                                for message in batch:
                                    try:
                                        msg_id = f"offline_{int(time.time() * 1000)}_{id(message)}"
                                        # Convert Message to dict if needed
                                        msg_dict = message.model_dump() if isinstance(message, Message) else message
                                        context = msg_dict.get('context', {})
                                        self.storage.store(
                                            msg_id,
                                            msg_dict.get('data', {}),
                                            tags=context.get('tags') if context else None,
                                            ttl=3600
                                        )
                                        if self.debug:
                                            print(f"Stored message offline: {msg_id}")
                                    except Exception as e:
                                        if self.debug:
                                            print(f"Failed to store message offline: {e}")

                    # Perform callback and message rate checks
                    if self.callback and self.check_msg_rate:
                        current_time = time.time() * 1000
                        if current_time >= (
                            self._last_msg_check + (self.check_msg_rate * 1000)
                        ):
                            self.check_msg()
                            self._last_msg_check = current_time
                    
                    # Send heartbeat if enabled and interval has passed
                    if self.send_heartbeat and self._connection_state:
                        current_time = time.time()
                        if (current_time - self._last_heartbeat) >= self.heartbeat_interval:
                            try:
                                self._send_heartbeat()
                                self._last_heartbeat = current_time
                            except Exception as e:
                                if self.debug:
                                    print(f"Heartbeat error: {e}")

                    # Sleep to avoid overloading the system if time spent is less than interval
                    elapsed_time = time.time() * 1000 - start_time
                    if elapsed_time < 250:
                        time.sleep((250 - elapsed_time) / 1000)

                # Cleanup expired messages every minute
                current_time = time.time() * 1000
                if current_time >= (self._last_cleanup + 60000):  # 60 seconds
                    if self.storage:
                        deleted_count = self.storage.cleanup_expired()
                        if self.debug and deleted_count > 0:
                            print(f"Cleaned up {deleted_count} expired offline messages")
                    self._last_cleanup = current_time

    def check_connection_state(self) -> bool:
        """Check if the client can connect to the server.
        
        Returns:
            bool: True if connection is available, False otherwise
        """
        try:
            if self.mode == "agent":
                # For agent mode, try platform-appropriate connection
                socket_path = self._get_socket_path()
                test_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                test_sock.settimeout(2)
                test_sock.connect(socket_path)
                test_sock.close()
                return True
            else:
                # For API mode, try a simple HEAD request
                response = self.client.head("/", timeout=2)
                return response.status_code < 500
        except (socket.error, ConnectionError, Exception):
            return False

    def process_offline_messages(self) -> None:
        """Process stored offline messages when connection is restored."""
        if not self.storage:
            return

        # Check how many messages we have
        total_count = self.storage.get_message_count()
        if total_count == 0:
            return

        if self.debug:
            print(f"Processing {total_count} offline messages in batches")

        # Process in batches to avoid memory/performance issues
        batch_size = 50  # Reasonable batch size
        processed = 0

        while processed < total_count:
            # Get a batch of messages
            stored_messages = self.storage.get_all_messages(limit=batch_size)
            if not stored_messages:
                break  # No more messages

            # Convert stored messages back to publishable format
            messages_to_send = []
            message_ids_to_delete = []

            for stored_msg in stored_messages:
                try:
                    # Parse the stored data back to dict
                    data = json.loads(stored_msg['data'])
                    tags = json.loads(stored_msg['tags']) if stored_msg['tags'] else None

                    # Create message in the expected format
                    message = make_message(data, "publish", tags=tags)
                    messages_to_send.append(message)
                    message_ids_to_delete.append(stored_msg['id'])
                except Exception as e:
                    if self.debug:
                        print(f"Error processing stored message {stored_msg['id']}: {e}")
                    # Delete corrupted message
                    message_ids_to_delete.append(stored_msg['id'])

            # Send the batch
            if messages_to_send:
                try:
                    self._publish_messages(messages_to_send)
                    # Only delete messages if they were sent successfully
                    self.storage.delete_messages(message_ids_to_delete)
                    processed += len(messages_to_send)
                    if self.debug:
                        print(f"Sent batch of {len(messages_to_send)} messages ({processed}/{total_count})")
                except Exception as e:
                    if self.debug:
                        print(f"Failed to send offline message batch: {e}")
                    break  # Stop processing if sending fails
            else:
                # Delete any corrupted messages and continue
                if message_ids_to_delete:
                    self.storage.delete_messages(message_ids_to_delete)
                    processed += len(message_ids_to_delete)
                break

        if self.debug and processed > 0:
            print(f"Finished processing offline messages: {processed} total")
    
    def _update_entity_status(self, online: bool) -> None:
        """Update entity online/offline status via API endpoint.
        
        Args:
            online: True to mark entity as online, False to mark as offline
        """
        if self.mode != "api":
            return  # Only works in API mode
        
        try:
            response = self.client.put(
                url="/entities/status",
                json={"online": online},
                timeout=5,
            )
            
            if response.status_code == 200:
                if self.debug:
                    status = "online" if online else "offline"
                    print(f"✅ Entity status updated to {status}")
            elif self.debug:
                print(f"⚠️ Failed to update entity status: {response.status_code} - {response.text}")
        except Exception as e:
            if self.debug:
                print(f"⚠️ Error updating entity status: {e}")
            # Don't raise - status update failures shouldn't break the client
    
    def _send_heartbeat(self) -> None:
        """Send a heartbeat message with system resource information.
        
        Creates a heartbeat message using Pydantic validation to ensure
        it matches the backend's expected format.
        """
        try:
            # Get system resource information
            resources = get_system_resources(bytes_only=True)
            
            # Create heartbeat data using Pydantic model for validation
            heartbeat_data = HeartbeatData(**resources)
            
            # Create heartbeat message with current UTC timestamp
            heartbeat_msg = HeartbeatMessage(
                msg_type="heartbeat",
                data=heartbeat_data,
                timestamp=datetime.now(ZoneInfo("UTC"))
            )
            
            # Convert to dict and publish
            heartbeat_dict = heartbeat_msg.model_dump()
            
            if self.debug:
                print(f"📤 Sending heartbeat: {heartbeat_dict}")
            
            # Publish heartbeat message directly (bypass queue for immediate delivery)
            self._publish_message(heartbeat_dict)
            
        except Exception as e:
            if self.debug:
                print(f"❌ Error sending heartbeat: {e}")
            # Don't raise - heartbeat failures shouldn't break the client
