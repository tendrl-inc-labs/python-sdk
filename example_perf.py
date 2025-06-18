import time

from tendrl import Client

def callback(msg):
    print(f"data: {msg.get('data')}")
    print(f"source: {msg.get('source')}")
    print(f"timestamp: {msg.get('timestamp')}")

client = Client(callback=callback, debug=True, max_batch_size=35, max_queue_size=500)
client.start()

payload = {
    'name': 'Hunter', 
    'age': 37,
    'role': 'Cloud Solutions Architect',
    'city': 'Birmingham',
    'state': 'AL'
}

@client.tether(tags=["write_to_dynamoDB", "other-thing"])
def tethered() -> dict: #Test Function for decoration
    return payload

while True:
    tethered()
    time.sleep(.01)
