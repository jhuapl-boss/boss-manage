# __init__
import configparser

CONFIG_FILE = "/etc/boss/boss.config"

class BossConfig:
    def __init__(self):
        self.config = configparser.ConfigParser()
        self.config.read(CONFIG_FILE)
        
    def __getitem__(self, key):
        return self.config[key]


# vault
import hvac

VAULT_SECTION = "vault"
VAULT_URL_KEY = "url"
VAULT_TOKEN_KEY = "token"

class Vault:
    def __init__(self, config = None):
        if config is None:
            self.config = BossConfig()
        else:
            self.config = config
            
        url = self.config[VAULT_SECTION][VAULT_URL_KEY]
        token = self.config[VAULT_SECTION][VAULT_TOKEN_KEY]
        
        self.client = hvac.Client(url=url, token=token)
        
        if not self.client.is_authenticated():
            raise Exception("Could not authenticate to Vault server")
            
    def logout(self):
        self.client.logout()
        self.client = None
    
    def read_dict(self, path):
        response = self.client.read(path)
        
        if response is None:
            raise Exception("Could not locate {} in Vault".format(path))
            
        return response["data"]
    
    def read(self, path, key):
        response = self.client.read(path)
        if response is not None:
            response = response["data"][key]
            
        if response is None:
            raise Exception("Could not locate {}/{} in Vault".format(path,key))
            
        return response
        
    def write(self, path, **kwargs):
        self.client.write(path, **kwargs)
        
    def delete(self, path):
        self.client.delete(path)