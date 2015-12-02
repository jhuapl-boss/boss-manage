import os
import json
import pprint

def domain_to_stackname(domain):
    return "".join(map(lambda x: x.capitalize(), domain.split(".")))

def template_argument(key, value, use_previous = False):
    return {"ParameterKey": key, "ParameterValue": value, "UsePreviousValue": use_previous}

def save_template(template, folder, domain):
    stack_name = domain_to_stackname(domain)
    
    with open(os.path.join(folder,stack_name + ".template"), "w") as fh:
        fh.write(template)
    
    
def create_template(parameters, resources, description=""):
    template = {
        "AWSTemplateFormatVersion" : "2010-09-09",
        "Description" : description,
        "Parameters": parameters,
        "Resources": resources
    }
    
    return json.dumps(template, indent=4)

def load_devices(*names, index=None):
    parameters = {}
    resources = {}
    
    for name in names:
        _param, _res = load_device(name, index)
        parameters.update(_param)
        resources.update(_res)
        
    return parameters, resources

def load_device(name, index=None, device_directory="devices", resources_suffix=".resources", parameters_suffix=".parameters"):
    resources_path = os.path.join(device_directory, name + resources_suffix)
    with open(resources_path, "r") as fh:
        data = fh.read()
        if index is not None:
            data = data.replace("{I}", index)
        resources = json.loads(data)
    
    parameters_path = os.path.join(device_directory, name + parameters_suffix)
    with open(parameters_path, "r") as fh:
        data = fh.read()
        if index is not None:
            data = data.replace("{I}", index)
        parameters = json.loads(data)
        
    return parameters, resources

def vpc_id_lookup(session, vpc_domain):
    client = session.client('ec2')
    response = client.describe_vpcs(Filters=[{"Name":"tag:Name", "Values":[vpc_domain]}])
    if len(response['Vpcs']) == 0:
        return None
    else:
        return response['Vpcs'][0]['VpcId']
        
    
def subnet_id_lookup(session, subnet_domain):
    client = session.client('ec2')
    response = client.describe_subnets(Filters=[{"Name":"tag:Name", "Values":[subnet_domain]}])
    if len(response['Subnets']) == 0:
        return None
    else:
        return response['Subnets'][0]['SubnetId']
        
def ami_lookup(session, ami_name):
    client = session.client('ec2')
    response = client.describe_images(Filters=[{"Name":"name", "Values":[ami_name]}])
    if len(response['Images']) == 0:
        return None
    else:
        return response['Images'][0]['ImageId']
        
def keypair_lookup(session):
    client = session.client('ec2')
    response = client.describe_key_pairs()
    print("Key Pairs")
    for i in range(len(response['KeyPairs'])):
        print("{}:  {}".format(i, response['KeyPairs'][i]['KeyName']))
    if len(response['KeyPairs']) == 0:
        return None
    while True:
        try:
            idx = input("[0]: ")
            idx = int(idx if len(idx) > 0 else "0")
            return response['KeyPairs'][idx]['KeyName']
        except:
            print("Invalid Key Pair number, try again")