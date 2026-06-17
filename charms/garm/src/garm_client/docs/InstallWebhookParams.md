# InstallWebhookParams


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**insecure_ssl** | **bool** |  | [optional] 
**webhook_endpoint_type** | **str** |  | [optional] 

## Example

```python
from garm_client.models.install_webhook_params import InstallWebhookParams

# TODO update the JSON string below
json = "{}"
# create an instance of InstallWebhookParams from a JSON string
install_webhook_params_instance = InstallWebhookParams.from_json(json)
# print the JSON string representation of the object
print(InstallWebhookParams.to_json())

# convert the object into a dict
install_webhook_params_dict = install_webhook_params_instance.to_dict()
# create an instance of InstallWebhookParams from a dict
install_webhook_params_from_dict = InstallWebhookParams.from_dict(install_webhook_params_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


