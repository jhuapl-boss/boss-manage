import boto3
import json
from urllib.request import build_opener, HTTPHandler, Request

def handler(event, context):
    print(event)

    if event['RequestType'] != 'Delete':
        send_response(event, context)
        return


    try:
        ec2 = boto3.client('ec2')

        stack_name = event['ResourceProperties']['StackName']

        resp = ec2.describe_subnets(
                    Filters = [
                        {'Name': 'tag:aws:cloudformation:stack-name',
                         'Values': [stack_name]},
                    ]
                )
        subnets = [subnet['SubnetId'] for subnet in resp['Subnets']]

        resp = ec2.describe_network_interfaces(
                    Filters = [
                        {'Name': 'subnet-id',
                         'Values': subnets},
                        {'Name': 'description',
                         'Values': ['AWS Lambda VPC ENI: *']},
                    ]
                )

        if len(resp['NetworkInterfaces']) == 0:
            print('No Lambda ENI to delete')
        else:
            for iface in resp['NetworkInterfaces']:
                if iface['Attachment']['Status'] == 'attached':
                    print('Detaching {}'.format(iface['PrivateIpAddress']))
                    ec2.detach_network_interface(AttachmentId = iface['Attachment']['AttachmentId'])

                print('Deleting {}'.format(iface['PrivateIpAddress']))
                ec2.delete_network_interface(NetworkInterfaceId = iface['NetworkInterfaceId'])
    except:
        send_response(event, context, failure = True)
        raise
    else:
        send_response(event, context)

def send_response(event, context, failure = False):
    # Taken from https://github.com/stelligent/cloudformation-custom-resources/blob/master/lambda/python/customresource.py
    response_body = json.dumps({
        "Status": 'FAILED' if failure else 'SUCCESS',
        "Reason": "See the details in CloudWatch Log Stream: " + context.log_stream_name,
        "PhysicalResourceId": context.log_stream_name,
        "StackId": event['StackId'],
        "RequestId": event['RequestId'],
        "LogicalResourceId": event['LogicalResourceId'],
        "Data": {}
    })

    print('ResponseURL: ', event['ResponseURL'])
    print('ResponseBody: ', response_body)

    response_body = response_body.encode()

    opener = build_opener(HTTPHandler)
    request = Request(event['ResponseURL'], data=response_body)
    request.add_header('Content-Type', '')
    request.add_header('Content-Length', len(response_body))
    request.get_method = lambda: 'PUT'
    response = opener.open(request)
    print("Status code: ", response.getcode())
    print("Status message: ", response.msg)
