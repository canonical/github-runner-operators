# ForgeEndpoint


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**api_base_url** | **str** |  | [optional] 
**base_url** | **str** |  | [optional] 
**ca_cert_bundle** | **bytes** |  | [optional] 
**created_at** | **datetime** |  | [optional] 
**description** | **str** |  | [optional] 
**endpoint_type** | **str** |  | [optional] 
**name** | **str** |  | [optional] 
**tools_metadata_url** | **str** |  | [optional] 
**updated_at** | **datetime** |  | [optional] 
**upload_base_url** | **str** |  | [optional] 
**use_internal_tools_metadata** | **bool** |  | [optional] 

## Example

```python
from garm_client.models.forge_endpoint import ForgeEndpoint

# TODO update the JSON string below
json = "{}"
# create an instance of ForgeEndpoint from a JSON string
forge_endpoint_instance = ForgeEndpoint.from_json(json)
# print the JSON string representation of the object
print(ForgeEndpoint.to_json())

# convert the object into a dict
forge_endpoint_dict = forge_endpoint_instance.to_dict()
# create an instance of ForgeEndpoint from a dict
forge_endpoint_from_dict = ForgeEndpoint.from_dict(forge_endpoint_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


