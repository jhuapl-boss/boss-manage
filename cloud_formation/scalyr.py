"""
Collect CloudWatch metrics for the given instance created during
CloudFormation.  The Scalyr monitor config file is updated based on the
instance provided.  The config file is stored here:

https://www.scalyr.com/file?path=%2Fscalyr%2Fmonitors

These environment variables MUST be set:
    scalyr_readconfig_token
    scalyr_writeconfig_token

"""

from boto3.session import Session
from copy import copy
import json
import subprocess
import library as lib

"""This file name used to store new config file before uploading to Scalyr."""
OUTPUT_CFG_FILE = 'scalyr-cfg.json'

"""Base monitor JSON object."""
EMPTY_MONITOR = {
    'type': 'cloudwatch',
    'region': '',
    'accessKey': '',                # User will need to fill in manually
    'secretKey': '',                # on Scalyr site.
    'executionIntervalMinutes': 5,
    'metrics': []
}


def add_instances_to_scalyr(session, region, instanceList):
    """
    Main entry point.  Pass a boto3 session, AWS region, and a list of host
    names to be monitored for the StatusCheckFailed CloudWatch metric.
    Returns True on success, False on failure.
    """
    try:
        raw = download_config_file()
        jsonCfg = json.loads(raw)
        # Boto3's docs say there's a Session.region_name attribute, but that
        # doesn't seem to be true.
        # monEle = get_cloudwatch_obj(jsonCfg, session.region_name)
        monEle = get_cloudwatch_obj(jsonCfg, region)
        metricsObj = get_metrics_obj(monEle)
        idList = convert_host_names_to_ids(session, instanceList)
        add_new_instances(metricsObj, idList)
        with open(OUTPUT_CFG_FILE, 'w') as f:
            json.dump(jsonCfg, f, indent=4)
        upload_config_file(OUTPUT_CFG_FILE)
        return True
    except subprocess.CalledProcessError as e:
        print_error(e.stderr.decode('UTF-8') )
    except Exception as e:
        print_error(e)

    # Indicate failure.
    return False

def print_error(msgStr):
    """
    Print specific error as given by msgStr and tell user that Scalyr must be
    configured manually.
    """
    print(msgStr)
    print('\nFailed to set up Scalyr monitoring of new instance(s).\nInstance(s) must be configured manually on https://www.scalyr.com\n\n')


def download_config_file():
    """
    Download the monitor config file from Scalyr and return it as a string.
    """
    cmd = ['./scalyr-tool', 'get-file', '/scalyr/monitors']
    complete = subprocess.run(cmd, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, check=True)

    return complete.stdout.decode('UTF-8')


def upload_config_file(filename):
    """
    Upload the monitor config file to Scalyr.
    """
    cmd = ['./scalyr-tool', 'put-file', '/scalyr/monitors']
    with open(filename, 'r') as f:
        complete = subprocess.run(cmd, stdin=f, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, check=True)


def load_config_file(fname):
    """Load a JSON file from disk and return it as a string."""
    try:
        f = open(fname, 'r')
    except OSError as e:
        print("Failed to open {}", fname)
        return ''
    strList = f.readlines()
    f.close()
    return ''.join(strList)


def create_default_monitor_obj(jsonObj, regionStr):
    """Used to create a default monitors array if it's missing or empty."""
    monitorObj = copy(EMPTY_MONITOR)
    monitorObj['region'] = regionStr
    jsonObj['monitors'] = [monitorObj]
    return monitorObj


def get_cloudwatch_obj(jsonObj, regionStr):
    """Find the element that configures cloudwatch for the given region."""
    try:
        monitorObj = jsonObj['monitors']
    except Exception as e:
        return create_default_monitor_obj(jsonObj, regionStr)

    if len(monitorObj) < 1:
        return create_default_monitor_obj(jsonObj, regionStr)

    for monitorItem in monitorObj:
        typeEle = monitorItem['type']
        if len(typeEle) < 1:
            continue
        if typeEle != 'cloudwatch':
            continue
        regionEle = monitorItem['region']
        if len(regionEle) < 1:
            continue
        if regionEle == regionStr:
            return monitorItem

    return None


def get_metrics_obj(monitorEle):
    """Find the metrics element within the given monitor element."""
    if monitorEle is None:
        return None
    metricsEle = monitorEle['metrics']
    if len(metricsEle) < 1:
        return None
    return metricsEle


def add_single_instance(metricsObj, idStr):
    """Add StatusCheckFailed monitoring for the given instance."""
    if metricsObj is None:
        return
    newMetric = {
        'namespace': 'AWS/EC2',
        'metric': 'StatusCheckFailed',
        'dimensions': { 'InstanceId': idStr }
    }
    metricsObj.append(newMetric)


def add_new_instances(metricsObj, idsList):
    """Add the list of instance IDs to the config file."""
    if metricsObj is None:
        return
    for i in idsList:
        add_single_instance(metricsObj, i)


def convert_host_names_to_ids(session, instanceList):
    """Look up ID of each instance on Amazon.  Returns a list of IDs."""
    idList = []
    for i in instanceList:
        instId = lib.instanceid_lookup(session, i)
        if instId is not None:
            idList.append(instId)
    return idList


# if __name__ == '__main__':
    # add_instances_to_scalyr(None, 'foo', [])
    # try:
    #     upload_config_file('foo')
    # except Exception as e:
    #     print_error(e)
    # val = download_config_file()
    # raw = load_config_file('cfg.json')
    # jsonCfg = json.loads(raw)
    # monEle = get_cloudwatch_obj(jsonCfg, 'us-east-1')
    # metricsObj = get_metrics_obj(monEle)
    # add_new_instances(metricsObj, ('blah', 'blah blah') )
    # with open(OUTPUT_CFG_FILE , 'w') as f:
    #     json.dump(jsonCfg, f, indent=4)
    # upload_config_file(OUTPUT_CFG_FILE)
