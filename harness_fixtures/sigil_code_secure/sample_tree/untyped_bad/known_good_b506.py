import yaml
from yaml import CSafeLoader
from yaml import SafeLoader
# no issue should be found
yaml.load("{}", SafeLoader)
yaml.load("{}", yaml.SafeLoader)
yaml.load("{}", CSafeLoader)
yaml.load("{}", yaml.CSafeLoader)
