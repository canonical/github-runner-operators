# ForgeInstance


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**agent_mode** | **bool** |  | [optional] 
**created_at** | **datetime** |  | [optional] 
**credentials** | [**ForgeCredentials**](ForgeCredentials.md) |  | [optional] 
**credentials_id** | **int** |  | [optional] 
**credentials_name** | **str** | CredentialName is the name of the credentials associated with the forge instance. This field is now deprecated. Use CredentialsID instead. This field will be removed in v0.2.0. | [optional] 
**endpoint** | [**ForgeEndpoint**](ForgeEndpoint.md) |  | [optional] 
**events** | [**List[EntityEvent]**](EntityEvent.md) |  | [optional] 
**id** | **str** |  | [optional] 
**pool** | [**List[Pool]**](Pool.md) |  | [optional] 
**pool_balancing_type** | **str** |  | [optional] 
**pool_manager_status** | [**PoolManagerStatus**](PoolManagerStatus.md) |  | [optional] 
**updated_at** | **datetime** |  | [optional] 

## Example

```python
from garm_client.models.forge_instance import ForgeInstance

# TODO update the JSON string below
json = "{}"
# create an instance of ForgeInstance from a JSON string
forge_instance_instance = ForgeInstance.from_json(json)
# print the JSON string representation of the object
print(ForgeInstance.to_json())

# convert the object into a dict
forge_instance_dict = forge_instance_instance.to_dict()
# create an instance of ForgeInstance from a dict
forge_instance_from_dict = ForgeInstance.from_dict(forge_instance_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


