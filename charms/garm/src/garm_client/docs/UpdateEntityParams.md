# UpdateEntityParams


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**agent_mode** | **bool** |  | [optional] 
**credentials_name** | **str** |  | [optional] 
**pool_balancer_type** | **str** |  | [optional] 
**webhook_secret** | **str** |  | [optional] 

## Example

```python
from garm_client.models.update_entity_params import UpdateEntityParams

# TODO update the JSON string below
json = "{}"
# create an instance of UpdateEntityParams from a JSON string
update_entity_params_instance = UpdateEntityParams.from_json(json)
# print the JSON string representation of the object
print(UpdateEntityParams.to_json())

# convert the object into a dict
update_entity_params_dict = update_entity_params_instance.to_dict()
# create an instance of UpdateEntityParams from a dict
update_entity_params_from_dict = UpdateEntityParams.from_dict(update_entity_params_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


