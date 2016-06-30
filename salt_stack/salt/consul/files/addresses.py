import boto3
import bossutils

bossutils.utils.set_excepthook()
log = bossutils.logger.BossLogger().logger

try:
    def where(xs, predicate):
        for x in xs:
            if predicate(x):
                return x
        return None

    def find_name(xs):
        tag = where(xs, lambda x: x['Key'] == "Name")
        return None if tag is None else tag['Value']

    url = bossutils.utils.METADATA_URL + "placement/availability-zone"
    region = bossutils.utils.read_url(url)[:-1]
    ec2 = boto3.client('ec2', region_name=region)
    config = bossutils.configuration.BossConfig()
    fqdn = config["system"]["fqdn"]
    fqdn = "consul." + fqdn.split(".", 1)[1]

    log.info("Gathering IP addresses for " + fqdn)

    response = ec2.describe_instances(
        Filters=[{"Name":"tag:Name", "Values":[fqdn]}]
    )

    addresses = []
    items = response['Reservations']
    if len(items) > 0:
        for i in items:
            item = i['Instances'][0]
            name = find_name(item['Tags'])
            log.info("Checking {}({}) for private IP address".format(item['InstanceId'], name))
            log.info("State: " + str(item['State']))
            if 'PrivateIpAddress' in item:
                addresses.append(item['PrivateIpAddress'])
            else:
                log.info("No private IP address")
    else:
        log.info("No instances returned")

    print(str(addresses).replace("'", '"')) # we want the json style list of addresses
except Exception as e:
    log.error("Problem gathering IP addresses", e)
    print([])