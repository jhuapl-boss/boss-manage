import os
import json
import pprint
import time
import hosts

def domain_to_stackname(domain):
    return "".join(map(lambda x: x.capitalize(), domain.split(".")))

def template_argument(key, value, use_previous = False):
    if value is None:
        raise Exception("Could not determine argument '{}'".format(key))
    return {"ParameterKey": key, "ParameterValue": value, "UsePreviousValue": use_previous}

def save_template(template, folder, domain):
    stack_name = domain_to_stackname(domain)
    
    with open(os.path.join(folder,stack_name + ".template"), "w") as fh:
        fh.write(template)

def cloudformation_create(session, name, template, arguments, wait=True):
    client = session.client('cloudformation')
    response = client.create_stack(
        StackName = name,
        TemplateBody = template,
        Parameters = arguments
    )
    
    rtn = True
    if wait:
        get_status = lambda r: r['Stacks'][0]['StackStatus']
        response = client.describe_stacks(StackName=name)
        if len(response['Stacks']) == 0:
            print("Problem launching stack")
        else:
            print("Waiting for create ", end="", flush=True)
            while get_status(response) == 'CREATE_IN_PROGRESS':
                time.sleep(5)
                print(".", end="", flush=True)
                response = client.describe_stacks(StackName=name)
            print(" done")

            if get_status(response) == 'CREATE_COMPLETE':
                print("Created stack '{}'".format(name))
            else:
                print("Status of stack '{}' is '{}'".format(name, get_status(response)))
                rtn = False
    return rtn

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
    
    # With composing multiple devices we may include resources
    # that are required by another device, if so we don't need
    # to include them as a parameter anymore
    for k in resources:
        if k in parameters:
            del parameters[k]
        
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

def _call_vault(command, input=None):
    import subprocess
        
    cmd = ["./bastion.py",
            "../packer/variables/aws-credentials",
            "/home/microns/.ssh/pryordm1-test.pem",
            "bastion.core.boss",
            "vault.core.boss",
            command]
            
    proc = subprocess.Popen(cmd,
                             cwd = "../vault/",
                             stdin = subprocess.PIPE,
                             stdout = subprocess.DEVNULL, # Supress output
                             stderr = subprocess.DEVNULL,
                             universal_newlines=True)
                             
    if input is not None:
        proc.communicate(input)
        
    proc.wait()
                             
    return proc.returncode
    
def generate_token():
    print("Generating vault access token...")
    result = _call_vault("vault-provision")
    
    file = "../vault/private/new_token"
    with open(file, "r") as fh:
        token = fh.read()
    os.remove(file) # prevent someone else reading the token
    
    return token
    
def revoke_token(token):
    print("Revoking vault access token...")
    _call_vault("vault-revoke", token + "\n")
    
def save_django(db, user, password, host, port):
    print("Saving Django database access information...")
    args = "\n".join([db, user, password, host, port])
    result = _call_vault("vault-django", args)
    
def add_userdata(resources, machine, data):
    resources[machine]["Properties"]["UserData"] = { "Fn::Base64" : data }

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
        
def sg_lookup(session, vpc_id, group_name):
    client = session.client('ec2')
    response = client.describe_security_groups(Filters=[{"Name":"vpc-id", "Values":[vpc_id]},
                                                        {"Name":"group-name", "Values":[group_name]}])
    if len(response['SecurityGroups']) == 0:
        return None
    else:
        return response['SecurityGroups'][0]['GroupId']
        
def rt_lookup(session, vpc_id, rt_name):
    client = session.client('ec2')
    response = client.describe_route_tables(Filters=[{"Name":"vpc-id", "Values":[vpc_id]},
                                                     {"Name":"tag:Name", "Values":[rt_name]}])
                                                     
    if len(response['RouteTables']) == 0:
        return None
    else:
        return response['RouteTables'][0]['RouteTableId']
        
def peering_lookup(session, from_id, to_id):
    client = session.client('ec2')
    response = client.describe_vpc_peering_connections(Filters=[{"Name":"requester-vpc-info.vpc-id", "Values":[from_id]},
                                                                {"Name":"requester-vpc-info.owner-id", "Values":["256215146792"]},
                                                                {"Name":"accepter-vpc-info.vpc-id", "Values":[to_id]},
                                                                {"Name":"accepter-vpc-info.owner-id", "Values":["256215146792"]},
                                                                {"Name":"status-code", "Values":["active"]},
                                                                ])
                                                                
    if len(response['VpcPeeringConnections']) == 0:
        return None
    else:
        return response['VpcPeeringConnections'][0]['VpcPeeringConnectionId']
        
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
            
def peer_route_update(session, from_vpc, to_vpc):
    from_id = vpc_id_lookup(session, from_vpc)
    to_id = vpc_id_lookup(session, to_vpc)
    peer_id = peering_lookup(session, from_id, to_id)
    print("peer {} -> {} = {}".format(from_id, to_id, peer_id))
    int_rt_id = rt_lookup(session, to_id, "internal")
    ext_rt_id = rt_lookup(session, to_id, "external")
    
    from_cidr = hosts.lookup(from_vpc)
    
    resource = session.resource('ec2')
    rt = resource.RouteTable(int_rt_id)
    rt.create_route(DestinationCidrBlock=from_cidr,
                    VpcPeeringConnectionId=peer_id)
    if ext_rt_id is not None:
        rt = resource.RouteTable(ext_rt_id)
        rt.create_route(DestinationCidrBlock=from_cidr,
                        VpcPeeringConnectionId=peer_id)

