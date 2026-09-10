# import dbm
import json
import logging
import os
import platform
from queue import Queue, Empty, Full as QueueFull
import socket
import threading
import time
from typing import Callable, List, Union

import httpx

from tendrl.utils import make_message
from tendrl.utils.utils import get_system_metrics, calculate_dynamic_batch_size
from .storage import SQLiteStorage

VERSION = "0.1.6"

# Undelivered messages are announced through the standard logging module, so an
# application can route them wherever its other logs go. With no logging set up
# at all, Python's last-resort handler still puts warnings on stderr, which is
# the point: a client that cannot deliver must not look like a healthy one.
logger = logging.getLogger("tendrl")

# A client that has lost its network would otherwise log on every batch. Report
# at most this often, and count what happened in between.
UNDELIVERED_REPORT_INTERVAL = 60  # seconds

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
        "_server_label",
        "_last_undelivered_report",
        "_held_since_report",
        "_dropped_since_report",
    )

    def __init__(
        self,
        mode: str = "api",
        api_key: str = None,
        app_url: str = None,
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
            self._server_label = self._get_socket_path()
            if self.debug:
                if self._is_windows:
                    print("Agent mode: Using AF_UNIX on Windows (requires Windows 10 1803+)")
                else:
                    print("Agent mode: Using AF_UNIX socket")
        elif self.mode == "api":
            api_key = api_key or os.getenv("TENDRL_KEY")
            if not api_key:
                raise APIException("No api_key provided and TENDRL_KEY env var not set")
            
            # Server URL: explicit app_url arg > TENDRL_APP_URL env > production.
            # Accepts either a bare origin ("http://192.168.1.50") or a full base
            # URL already ending in /api, so the same value works everywhere.
            # Without this the SDK could only ever reach production, which made it
            # impossible to test against staging or a local stack.
            origin = (app_url or os.getenv("TENDRL_APP_URL") or "https://app.tendrl.com").rstrip("/")
            if not origin.endswith("/api"):
                origin += "/api"

            self._server_label = origin
            self.client = httpx.Client(
                http2=True,
                base_url=origin,
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

        # Undelivered-message accounting, read by _report_undelivered.
        self._last_undelivered_report = 0.0
        self._held_since_report = 0
        self._dropped_since_report = 0

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
                        return
                    if response.status_code != 200:
                        return
                    if self.callback:
                        # This may need to be ran in another thread or async, it could kill the program..or a timeout
                        # I think could make a decorator to wrap this as like a middleware, if it is a server event, have server cb like in MP
                        messages = response.json().get("messages")
                        if messages:
                            if self.check_msg_limit == 1:
                                self.callback(messages[0])
                            else:
                                for message in messages:
                                    try:
                                        self.callback(message)
                                    except Exception as e:
                                        if self.debug:
                                            print(f"error in callback: {e}")
                except httpx.HTTPError as error:
                    if self.debug:
                        print(f"httpx error: {error}")
                    return None
        except json.JSONDecodeError:
            if self.debug:
                print("Failed to decode JSON from response.")
        except socket.error as e:
            if self.debug:
                print(f"Socket error: {e}")

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

    def stop(self):
        """Stop the client and cleanup resources."""
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
            message: Message to publish
            timeout: Request timeout in seconds

        Returns:
            The server's reply, if it sent one. Note that a reply is not proof
            of delivery: the server sends no body on some successful posts, so
            a bare None cannot be told apart from a failure. That is why a
            failure is reported here rather than left to the caller to infer.
        """
        result, delivered = self._send_one(message, timeout=timeout)
        if not delivered:
            self._report_undelivered(dropped=1)
        return result

    def _send_one(self, message, timeout: int = 5):
        """Send one message and say whether it arrived.

        Returns:
            (result, delivered). `result` is what _publish_message hands back to
            the caller; `delivered` is what the sender loop needs, because
            publish() returns before the send happens and so cannot report a
            failure itself.
        """
        try:
            if self.mode == "agent":
                original_timeout = self.sock.gettimeout() if timeout else None

                try:
                    self.sock.sendall(json.dumps(message).encode("utf-8"))
                    if message.get("context", {}).get("wait"):
                        msg_id = json.loads(self.sock.recv(1024).decode()).get("id")
                        return msg_id, True
                except socket.timeout as err:
                    return str(f"error: {err.errno}"), False
                except socket.error as e:
                    if e.errno == 32:  # Broken pipe
                        raise ConnectionError(
                            "Failed to connect to Tendrl Server"
                        ) from e

                if original_timeout:
                    self.sock.settimeout(original_timeout)

                return None, True

            else:  # HTTP Client Mode
                response = self.client.post(
                    url="/entities/message",
                    json=message,
                    timeout=timeout,
                )

                if response.status_code != 200:
                    if self.debug:
                        print(f"Request failed with status {response.status_code}")
                    return None, False

                return (response.json() if response.content else None), True
        except httpx.HTTPError as error:
            return error, False
        except socket.error as e:
            if self.debug:
                print(f"Agent Socket Error: {e}")
            return None, False

    def _publish_messages(self, messages: List[dict]) -> List[dict]:
        """Publish a batch of messages to the server.

        Args:
            messages: List of messages to publish

        Returns:
            The messages that did not reach the server, for the caller to
            persist or report. Delivery used to be assumed, which is how a
            failed batch could disappear without a trace.
        """
        if not messages:
            return []
            
        # Check if any messages require individual handling (wait_response=True)
        individual_messages = []
        batch_messages = []
        
        for message in messages:
            if message.get("context", {}).get("wait"):
                individual_messages.append(message)
            else:
                batch_messages.append(message)
        
        undelivered = []

        # Send batch messages using the batch endpoint
        if batch_messages:
            if self.mode == "agent":
                # For agent mode, send individual messages (no batch support in socket protocol)
                for message in batch_messages:
                    if not self._send_one(message)[1]:
                        undelivered.append(message)
            else:
                try:
                    # Use batch endpoint for HTTP API
                    response = self.client.post(
                        url="/entities/messages",  # Batch endpoint
                        json={"messages": batch_messages},
                        timeout=30,  # Longer timeout for batch requests
                    )
                    if response.status_code != 200:
                        if self.debug:
                            print(f"Batch request failed with status {response.status_code}")
                        undelivered.extend(batch_messages)
                except Exception as e:
                    if self.debug:
                        print(f"Batch request failed: {e}, falling back to individual requests")
                    # Fallback to individual requests
                    for message in batch_messages:
                        if not self._send_one(message)[1]:
                            undelivered.append(message)

        # Send individual messages that require wait_response
        for message in individual_messages:
            if not self._send_one(message)[1]:
                undelivered.append(message)

        return undelivered

    def _handle_undelivered(self, messages: List[dict]) -> None:
        """Persist messages that did not reach the server, and report them.

        Offline storage used to be reached only when the periodic probe had
        already marked the connection down, so a send that failed on its own --
        including every send in the first thirty seconds of a client's life --
        bypassed it entirely.
        """
        held = 0
        dropped = 0
        for message in messages:
            if self.storage:
                try:
                    msg_id = f"offline_{int(time.time() * 1000)}_{id(message)}"
                    self.storage.store(
                        msg_id,
                        message.get('data', {}),
                        tags=message.get('tags'),
                        ttl=3600
                    )
                    if self.debug:
                        print(f"Stored message offline: {msg_id}")
                    held += 1
                    continue
                except Exception as e:
                    if self.debug:
                        print(f"Failed to store message offline: {e}")
            dropped += 1

        self._report_undelivered(held=held, dropped=dropped)

    def _report_undelivered(self, held: int = 0, dropped: int = 0) -> None:
        """Announce undelivered messages, at most once a minute.

        publish() is asynchronous, so nothing the caller holds can report a
        delivery failure. Without this, a wrong URL, a dead network or a
        rejected key produced a client that looked entirely healthy while its
        data went missing.
        """
        self._held_since_report += held
        self._dropped_since_report += dropped

        now = time.time()
        if now - self._last_undelivered_report < UNDELIVERED_REPORT_INTERVAL:
            return
        self._last_undelivered_report = now

        held, dropped = self._held_since_report, self._dropped_since_report
        self._held_since_report = 0
        self._dropped_since_report = 0

        if dropped:
            logger.warning(
                "Tendrl: DROPPED %d message(s) that could not be delivered to %s. "
                "Set offline_storage=True to hold undelivered messages for retry "
                "instead of losing them.",
                dropped, self._server_label,
            )
        if held:
            logger.warning(
                "Tendrl: could not deliver %d message(s) to %s; held in offline "
                "storage and retried when the connection returns.",
                held, self._server_label,
            )

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

                    # Collect up to batch_size messages from the queue.
                    # stop() enqueues None as a shutdown sentinel; batching it
                    # crashed this thread on message.get("context") and took the
                    # rest of the batch down with it, so drop it here.
                    stopping = False
                    while len(batch) < dynamic_batch_size and not self.queue.empty():
                        try:
                            msg = self.queue.get(timeout=batch_interval)
                            self.queue.task_done()
                            if msg is None:
                                stopping = True
                                break
                            batch.append(msg)
                        except Empty:
                            break

                    if batch:
                        if self.debug:
                            print(
                                f"Queue load: {metrics.queue_load:.1f}%, CPU: {metrics.cpu_usage:.1f}%, "
                                f"Memory: {metrics.memory_usage:.1f}%, Batch size: {len(batch)}"
                            )

                        # Only attempt a send if the last probe found a server.
                        if self._connection_state:
                            undelivered = self._publish_messages(batch)
                        else:
                            undelivered = batch

                        if undelivered:
                            self._handle_undelivered(undelivered)

                    # A shutdown sentinel means stop() is waiting on this
                    # thread: flush what was already collected, then leave
                    # rather than idling out the remaining interval.
                    if stopping:
                        return

                    # Perform callback and message rate checks
                    if self.callback and self.check_msg_rate:
                        current_time = time.time() * 1000
                        if current_time >= (
                            self._last_msg_check + (self.check_msg_rate * 1000)
                        ):
                            self.check_msg()
                            self._last_msg_check = current_time

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
            send_ids = []          # storage ids, parallel to messages_to_send
            corrupt_ids = []       # unparseable rows, dropped either way

            for stored_msg in stored_messages:
                try:
                    # Parse the stored data back to dict
                    data = json.loads(stored_msg['data'])
                    tags = json.loads(stored_msg['tags']) if stored_msg['tags'] else None

                    # Create message in the expected format
                    message = make_message(data, "publish", tags=tags)
                    messages_to_send.append(message)
                    send_ids.append(stored_msg['id'])
                except Exception as e:
                    if self.debug:
                        print(f"Error processing stored message {stored_msg['id']}: {e}")
                    # Delete corrupted message
                    corrupt_ids.append(stored_msg['id'])

            if corrupt_ids:
                self.storage.delete_messages(corrupt_ids)
                processed += len(corrupt_ids)

            # Send the batch
            if messages_to_send:
                try:
                    undelivered = self._publish_messages(messages_to_send)
                except Exception as e:
                    if self.debug:
                        print(f"Failed to send offline message batch: {e}")
                    break  # Stop processing if sending fails

                # Delete only what actually arrived. Deleting the whole batch
                # regardless is how a flapping connection used to erase stored
                # messages it had never managed to send.
                still_queued = {id(m) for m in undelivered}
                delivered_ids = [
                    stored_id
                    for message, stored_id in zip(messages_to_send, send_ids)
                    if id(message) not in still_queued
                ]
                if delivered_ids:
                    self.storage.delete_messages(delivered_ids)
                    processed += len(delivered_ids)
                    if self.debug:
                        print(f"Sent batch of {len(delivered_ids)} messages ({processed}/{total_count})")

                if undelivered:
                    # They stay in storage, so this is a retry, not a loss.
                    self._report_undelivered(held=len(undelivered))
                    break
            elif not corrupt_ids:
                break

        if self.debug and processed > 0:
            print(f"Finished processing offline messages: {processed} total")
