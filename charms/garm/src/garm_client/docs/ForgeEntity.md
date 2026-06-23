# ForgeEntity


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**agent_mode** | **bool** |  | [optional] 
**created_at** | **datetime** |  | [optional] 
**credentials** | [**ForgeCredentials**](ForgeCredentials.md) |  | [optional] 
**entity_type** | **str** |  | [optional] 
**id** | **str** |  | [optional] 
**name** | **str** |  | [optional] 
**owner** | **str** |  | [optional] 
**pool_balancing_type** | **str** |  | [optional] 
**pool_manager_status** | [**PoolManagerStatus**](PoolManagerStatus.md) |  | [optional] 
**updated_at** | **datetime** |  | [optional] 

## Example

```python
from garm_client.models.forge_entity import ForgeEntity

# TODO update the JSON string below
json = "{}"
# create an instance of ForgeEntity from a JSON string
forge_entity_instance = ForgeEntity.from_json(json)
# print the JSON string representation of the object
print(ForgeEntity.to_json())

# convert the object into a dict
forge_entity_dict = forge_entity_instance.to_dict()
# create an instance of ForgeEntity from a dict
forge_entity_from_dict = ForgeEntity.from_dict(forge_entity_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


