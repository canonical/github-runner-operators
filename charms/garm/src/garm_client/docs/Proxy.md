# Proxy


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**created_at** | **datetime** |  | [optional] 
**description** | **str** |  | [optional] 
**http_proxy** | **str** | HTTPProxy is the proxy URL used for plain HTTP requests. | [optional] 
**https_proxy** | **str** | HTTPSProxy is the proxy URL used for HTTPS requests. | [optional] 
**id** | **int** |  | [optional] 
**name** | **str** |  | [optional] 
**no_proxy** | **str** | NoProxy is a comma separated list of hosts, domains or CIDRs for which the proxy should be bypassed. | [optional] 
**updated_at** | **datetime** |  | [optional] 
**username** | **str** | Username is the username used to authenticate to the proxy. If set, it will be composed into the final proxy URLs handed to runners. | [optional] 

## Example

```python
from garm_client.models.proxy import Proxy

# TODO update the JSON string below
json = "{}"
# create an instance of Proxy from a JSON string
proxy_instance = Proxy.from_json(json)
# print the JSON string representation of the object
print(Proxy.to_json())

# convert the object into a dict
proxy_dict = proxy_instance.to_dict()
# create an instance of Proxy from a dict
proxy_from_dict = Proxy.from_dict(proxy_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


