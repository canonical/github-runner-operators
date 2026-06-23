# AgentCapabilities


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**has_shell** | **bool** |  | [optional] 

## Example

```python
from garm_client.models.agent_capabilities import AgentCapabilities

# TODO update the JSON string below
json = "{}"
# create an instance of AgentCapabilities from a JSON string
agent_capabilities_instance = AgentCapabilities.from_json(json)
# print the JSON string representation of the object
print(AgentCapabilities.to_json())

# convert the object into a dict
agent_capabilities_dict = agent_capabilities_instance.to_dict()
# create an instance of AgentCapabilities from a dict
agent_capabilities_from_dict = AgentCapabilities.from_dict(agent_capabilities_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


