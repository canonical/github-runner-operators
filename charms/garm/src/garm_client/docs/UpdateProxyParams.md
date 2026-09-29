# UpdateProxyParams


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**description** | **str** |  | [optional] 
**http_proxy** | **str** | HTTPProxy is the proxy URL used for plain HTTP requests. | [optional] 
**https_proxy** | **str** | HTTPSProxy is the proxy URL used for HTTPS requests. | [optional] 
**name** | **str** |  | [optional] 
**no_proxy** | **str** | NoProxy is a comma separated list of hosts, domains or CIDRs for which the proxy should be bypassed. Setting it to an empty string clears the value. | [optional] 
**password** | **str** | Password is the password used to authenticate to the proxy. Setting it to an empty string clears the password. | [optional] 
**username** | **str** | Username is the username used to authenticate to the proxy. Setting it to an empty string clears the proxy credentials. | [optional] 

## Example

```python
from garm_client.models.update_proxy_params import UpdateProxyParams

# TODO update the JSON string below
json = "{}"
# create an instance of UpdateProxyParams from a JSON string
update_proxy_params_instance = UpdateProxyParams.from_json(json)
# print the JSON string representation of the object
print(UpdateProxyParams.to_json())

# convert the object into a dict
update_proxy_params_dict = update_proxy_params_instance.to_dict()
# create an instance of UpdateProxyParams from a dict
update_proxy_params_from_dict = UpdateProxyParams.from_dict(update_proxy_params_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


