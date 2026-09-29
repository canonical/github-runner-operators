# CreateForgeInstanceParams


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**agent_mode** | **bool** |  | [optional] 
**credentials_name** | **str** |  | [optional] 
**endpoint_name** | **str** |  | [optional] 
**forge_type** | **str** |  | [optional] 
**pool_balancer_type** | **str** |  | [optional] 
**webhook_secret** | **str** |  | [optional] 

## Example

```python
from garm_client.models.create_forge_instance_params import CreateForgeInstanceParams

# TODO update the JSON string below
json = "{}"
# create an instance of CreateForgeInstanceParams from a JSON string
create_forge_instance_params_instance = CreateForgeInstanceParams.from_json(json)
# print the JSON string representation of the object
print(CreateForgeInstanceParams.to_json())

# convert the object into a dict
create_forge_instance_params_dict = create_forge_instance_params_instance.to_dict()
# create an instance of CreateForgeInstanceParams from a dict
create_forge_instance_params_from_dict = CreateForgeInstanceParams.from_dict(create_forge_instance_params_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


