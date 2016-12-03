"""
??? right now with AWSNames there is a single representation for all uses of a given resource

What about creating 
class AWSName:
    def __init__(self, name (hostname?)):
        self.name = name

    def __str__(self):
        return self.name

    @property
    def dns(self):
        return self.name

    @property
    def ec2(self):
        return self.name

    @property
    def rds(self):
        return self.name.replace('.','-')

    ..... repeat for each service that uses the name .....
"""
class AWSNames(object):
    def __init__(self, base):
        self.base = base
        self.base_dot = '.' + base
        self.base_dash = '-' + base.replace('.', '-')

    def _ec2(self, name):
        return name + self.base_dot

    def _rds(self, name):
        # while RDS instance ids can't contain '.', the DNS
        # names for those instances will contain '.'
        return name + self.base_dot

    def _dynamodb(self, name):
        return name

    def _redis(self, name):
        return name

    def _sg(self, name):
        return name + self.base_dot

    def _rt(self, name):
        return name + self.base_dot

    def _inet_gw(self, name):
        return name + self.base_dot

    def _elb(self, name):
        return name + self.base_dot

    def _asg(self, name):
        return name

    @property
    def auth(self):
        return self._ec2("auth")

    @property
    def vault(self):
        return self._ec2("vault")

    @property
    def consul(self):
        return self._ec2("consul")

    @property
    def endpoint(self):
        return self._ec2("endpoint")

    @property
    def endpoint_db(self):
        return self._rds("endpoint-db")
