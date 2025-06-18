import sys
import time

from tendrl import Client

client = Client(debug=True)
client.start()

payload = {
    'name': 'Hunter', 
    'age': 37,
    'role': 'Cloud Solutions Architect',
    'city': 'Birmingham',
    'state': 'AL'
}

@client.tether(tags=["test_tag"])
def tethered() -> dict: #Test Function for decoration
    time.sleep(1.5) #Simulate work

    return payload

while True:
    try:
        m = client.publish("Test String", wait_response=True) #Send string, wait response
        print(m)
        time.sleep(5)

        tethered() # user decorator, queues a batches sending
        time.sleep(2)
        sys.exit()
    except KeyboardInterrupt:
        client.stop()
        sys.exit()
