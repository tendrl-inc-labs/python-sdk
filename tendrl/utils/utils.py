import datetime
#import platform
import socket
from typing import Union
from zoneinfo import ZoneInfo
import psutil


class SystemMetrics:
    """System resource metrics for dynamic batch processing."""

    def __init__(self):
        self.cpu_usage = 0.0
        self.memory_usage = 0.0
        self.queue_load = 0.0


MSG_TYPES = (
    "publish",
    "heartbeat",
    "server_cmd_req",
    "client_cmd_resp",
)

def get_system_metrics(queue_size: int, max_queue_size: int) -> SystemMetrics:
    """Get current system resource metrics.

    Args:
        queue_size: Current queue size
        max_queue_size: Maximum queue size

    Returns:
        SystemMetrics: Current CPU, memory and queue metrics
    """
    metrics = SystemMetrics()
    metrics.cpu_usage = psutil.cpu_percent(interval=0.1)
    metrics.memory_usage = psutil.virtual_memory().percent
    metrics.queue_load = (queue_size / max_queue_size) * 100 if max_queue_size > 0 else 0
    return metrics


def calculate_dynamic_batch_size(
    metrics: SystemMetrics,
    target_cpu_percent: float = 65.0,
    target_mem_percent: float = 75.0,
    min_batch_size: int = 10,
    max_batch_size: int = 100
) -> int:
    """Calculate optimal batch size based on system metrics.

    Args:
        metrics: Current system metrics
        target_cpu_percent: Target CPU usage percentage
        target_mem_percent: Target memory usage percentage
        min_batch_size: Minimum batch size
        max_batch_size: Maximum batch size

    Returns:
        int: Calculated batch size between min and max bounds
    """
    # Use nonlinear scaling for CPU and memory factors
    cpu_factor = max(0, 1 - (metrics.cpu_usage / target_cpu_percent) ** 2)
    mem_factor = max(0, 1 - (metrics.memory_usage / target_mem_percent) ** 2)

    # Reduce the impact of queue factor
    queue_factor = min(1, metrics.queue_load / 100)

    # Combine factors with dynamic weighting
    total_usage = metrics.cpu_usage + metrics.memory_usage + metrics.queue_load
    cpu_weight = 0.5 if metrics.cpu_usage > 50 else 0.4
    mem_weight = 0.5 if metrics.memory_usage > 50 else 0.4
    queue_weight = 0.2 if total_usage < 150 else 0.1

    resource_factor = (
        cpu_factor * cpu_weight + mem_factor * mem_weight + queue_factor * queue_weight
    )

    # Calculate new batch size
    new_batch_size = int(max_batch_size * resource_factor)

    # Early return for trivial cases
    if metrics.cpu_usage < 30 and metrics.memory_usage < 30 and metrics.queue_load < 25:
        return max_batch_size

    # Ensure we stay within bounds
    return max(min_batch_size, min(new_batch_size, max_batch_size))


def make_message(
    data,
    msg_type,
    tags=None,
    entity="",
    timestamp=None,
    wait_response=False,
):
    """Create a message in the format expected by the Tendrl API.
    
    Args:
        data: Message data (str or dict)
        msg_type: Type of message
        tags: Optional list of string tags
        entity: Optional destination entity
        timestamp: Optional timestamp (will use current UTC if not provided)
        wait_response: Whether to wait for response
        
    Returns:
        dict: Formatted message
    """
    if not isinstance(data, (str, dict)):
        raise TypeError("Allowed types: ['str', 'dict']")
    if not tags:
        tags = []
    else:
        if not all(isinstance(i, str) for i in tags):
            raise TypeError("tags must be of type 'str'")
    
    context = {"tags": tags} if tags else {}
    if wait_response and not entity:
        context["wait"] = True
    
    m = {
        "msg_type": msg_type,
        "data": data,
        "context": context,
        "dest": entity,
        "timestamp": datetime.datetime.now(ZoneInfo("UTC")).isoformat(
            timespec="milliseconds"
        ) if not timestamp else timestamp,
    }
    return {k: v for k, v in m.items() if v}

def connect(api_key: str, mode: str) -> bool:
    if not internet():
        return False
    #e_type = f"{mode}:" + platform.version()

def internet(host="8.8.8.8", port=443, timeout=3):
    """
    Host: 8.8.8.8 (google-public-dns-a.google.com)
    OpenPort: 53/tcp
    Service: domain (DNS/TCP)
    """
    try:
        socket.setdefaulttimeout(timeout)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
        return True
    except socket.error as error:
        print(error)
        return False
