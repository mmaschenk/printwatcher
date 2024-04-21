#!/usr/bin/env python

import pika
import json
import time
import datetime
import os

from dotenv import load_dotenv

load_dotenv()

"""
This script reads the prusalink exchange and transforms the message to an RFC8428-compliant message
that will be placed on the output EXCHANGE.
"""

mqrabbit_user = os.getenv("MQRABBIT_USER")
mqrabbit_password = os.getenv("MQRABBIT_PASSWORD")
mqrabbit_host = os.getenv("MQRABBIT_HOST")
mqrabbit_vhost = os.getenv("MQRABBIT_VHOST")
mqrabbit_port = os.getenv("MQRABBIT_PORT")
mqrabbit_exchange = os.getenv("MQRABBIT_EXCHANGE")
mqrabbit_rgbexchange = os.getenv("MQRABBIT_RGBEXCHANGE")

print(f"rgbex: {mqrabbit_rgbexchange}")
everythingfine = True

def callback(ch, method, properties, body):
    print(f"[W] Handling: {body}")

    try:
        input = json.loads(body)
        print(f"[W] Parsed: {input}")

        if input['machine']['printer'] in [ 'mk3', 'mk4' ]:

            state = input['state']
            if state['printstate'] == 'printing':
                statusline = f"{input['machine']['printer']}:P {state['stillprinting']//3600}:{(state['stillprinting']//60)%60}"
            elif state['printstate'] == 'idle' and 'cooldowntimeout' in state:
                statusline = f"{input['machine']['printer']}:CD {state['temperature']['bed']}"
            elif state['printstate'] == 'idle':
                statusline = f"{input['machine']['printer']}: idle"
            elif state['printstate'] == 'unknown':
                statusline = ""

            message = { 
                'type': input['machine']['printer'], 
                'list': [
                    {
                        'text': statusline,
                        'color': 'cc4400'},
                ],
                'key': input['machine']['printer'], 
            }
            print(f"Going to send: {message}")
            m = json.dumps(message)
            print(f"json: {m}")
            channel.basic_publish(exchange=mqrabbit_rgbexchange, routing_key='*', body=json.dumps(message))

        ch.basic_ack(delivery_tag = method.delivery_tag)
    except Exception as e:
        print(f"[W]: errored {e}")

print("[R] Connecting")
mqrabbit_credentials = pika.PlainCredentials(mqrabbit_user, mqrabbit_password)
mqparameters = pika.ConnectionParameters(
    host=mqrabbit_host,
    virtual_host=mqrabbit_vhost,
    port=mqrabbit_port,
    credentials=mqrabbit_credentials)

mqconnection = pika.BlockingConnection(mqparameters)
channel = mqconnection.channel()

queuename = 'prusalink_prusargb_' + datetime.datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
q = channel.queue_declare(queue=queuename, exclusive=True, auto_delete=True)
channel.queue_bind(exchange=mqrabbit_exchange, queue=q.method.queue)

channel.basic_consume(queue=queuename, on_message_callback=callback)

print('[R] Waiting for messages. To exit press CTRL+C')
channel.start_consuming()