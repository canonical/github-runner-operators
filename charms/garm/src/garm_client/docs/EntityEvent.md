# EntityEvent


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**created_at** | **datetime** |  | [optional] 
**event_level** | **str** |  | [optional] 
**event_type** | **str** |  | [optional] 
**id** | **int** |  | [optional] 
**message** | **str** |  | [optional] 

## Example

```python
from garm_client.models.entity_event import EntityEvent

# TODO update the JSON string below
json = "{}"
# create an instance of EntityEvent from a JSON string
entity_event_instance = EntityEvent.from_json(json)
# print the JSON string representation of the object
print(EntityEvent.to_json())

# convert the object into a dict
entity_event_dict = entity_event_instance.to_dict()
# create an instance of EntityEvent from a dict
entity_event_from_dict = EntityEvent.from_dict(entity_event_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


