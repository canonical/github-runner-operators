# Enterprise


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**agent_mode** | **bool** |  | [optional] 
**created_at** | **datetime** |  | [optional] 
**credentials** | [**ForgeCredentials**](ForgeCredentials.md) |  | [optional] 
**credentials_id** | **int** |  | [optional] 
**credentials_name** | **str** | CredentialName is the name of the credentials associated with the enterprise. This field is now deprecated. Use CredentialsID instead. This field will be removed in v0.2.0. | [optional] 
**endpoint** | [**ForgeEndpoint**](ForgeEndpoint.md) |  | [optional] 
**events** | [**List[EntityEvent]**](EntityEvent.md) |  | [optional] 
**id** | **str** |  | [optional] 
**name** | **str** |  | [optional] 
**pool** | [**List[Pool]**](Pool.md) |  | [optional] 
**pool_balancing_type** | **str** |  | [optional] 
**pool_manager_status** | [**PoolManagerStatus**](PoolManagerStatus.md) |  | [optional] 
**updated_at** | **datetime** |  | [optional] 

## Example

```python
from garm_client.models.enterprise import Enterprise

# TODO update the JSON string below
json = "{}"
# create an instance of Enterprise from a JSON string
enterprise_instance = Enterprise.from_json(json)
# print the JSON string representation of the object
print(Enterprise.to_json())

# convert the object into a dict
enterprise_dict = enterprise_instance.to_dict()
# create an instance of Enterprise from a dict
enterprise_from_dict = Enterprise.from_dict(enterprise_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


