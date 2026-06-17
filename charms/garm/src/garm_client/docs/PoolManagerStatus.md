# PoolManagerStatus


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**failure_reason** | **str** |  | [optional] 
**running** | **bool** |  | [optional] 

## Example

```python
from garm_client.models.pool_manager_status import PoolManagerStatus

# TODO update the JSON string below
json = "{}"
# create an instance of PoolManagerStatus from a JSON string
pool_manager_status_instance = PoolManagerStatus.from_json(json)
# print the JSON string representation of the object
print(PoolManagerStatus.to_json())

# convert the object into a dict
pool_manager_status_dict = pool_manager_status_instance.to_dict()
# create an instance of PoolManagerStatus from a dict
pool_manager_status_from_dict = PoolManagerStatus.from_dict(pool_manager_status_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


