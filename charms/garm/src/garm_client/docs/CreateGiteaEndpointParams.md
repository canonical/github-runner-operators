# CreateGiteaEndpointParams


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**api_base_url** | **str** |  | [optional] 
**base_url** | **str** |  | [optional] 
**ca_cert_bundle** | **List[int]** |  | [optional] 
**description** | **str** |  | [optional] 
**name** | **str** |  | [optional] 
**tools_metadata_url** | **str** |  | [optional] 
**use_internal_tools_metadata** | **bool** |  | [optional] 

## Example

```python
from garm_client.models.create_gitea_endpoint_params import CreateGiteaEndpointParams

# TODO update the JSON string below
json = "{}"
# create an instance of CreateGiteaEndpointParams from a JSON string
create_gitea_endpoint_params_instance = CreateGiteaEndpointParams.from_json(json)
# print the JSON string representation of the object
print(CreateGiteaEndpointParams.to_json())

# convert the object into a dict
create_gitea_endpoint_params_dict = create_gitea_endpoint_params_instance.to_dict()
# create an instance of CreateGiteaEndpointParams from a dict
create_gitea_endpoint_params_from_dict = CreateGiteaEndpointParams.from_dict(create_gitea_endpoint_params_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


