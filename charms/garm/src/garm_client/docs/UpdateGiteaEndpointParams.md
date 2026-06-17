# UpdateGiteaEndpointParams


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**api_base_url** | **str** |  | [optional] 
**base_url** | **str** |  | [optional] 
**ca_cert_bundle** | **List[int]** |  | [optional] 
**description** | **str** |  | [optional] 
**tools_metadata_url** | **str** |  | [optional] 
**use_internal_tools_metadata** | **bool** |  | [optional] 

## Example

```python
from garm_client.models.update_gitea_endpoint_params import UpdateGiteaEndpointParams

# TODO update the JSON string below
json = "{}"
# create an instance of UpdateGiteaEndpointParams from a JSON string
update_gitea_endpoint_params_instance = UpdateGiteaEndpointParams.from_json(json)
# print the JSON string representation of the object
print(UpdateGiteaEndpointParams.to_json())

# convert the object into a dict
update_gitea_endpoint_params_dict = update_gitea_endpoint_params_instance.to_dict()
# create an instance of UpdateGiteaEndpointParams from a dict
update_gitea_endpoint_params_from_dict = UpdateGiteaEndpointParams.from_dict(update_gitea_endpoint_params_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


