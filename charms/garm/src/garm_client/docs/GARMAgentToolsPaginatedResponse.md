# GARMAgentToolsPaginatedResponse


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**current_page** | **int** |  | [optional] 
**next_page** | **int** |  | [optional] 
**pages** | **int** |  | [optional] 
**previous_page** | **int** |  | [optional] 
**results** | [**List[GARMAgentToolsPaginatedResponseResultsInner]**](GARMAgentToolsPaginatedResponseResultsInner.md) |  | [optional] 
**total_count** | **int** |  | [optional] 

## Example

```python
from garm_client.models.garm_agent_tools_paginated_response import GARMAgentToolsPaginatedResponse

# TODO update the JSON string below
json = "{}"
# create an instance of GARMAgentToolsPaginatedResponse from a JSON string
garm_agent_tools_paginated_response_instance = GARMAgentToolsPaginatedResponse.from_json(json)
# print the JSON string representation of the object
print(GARMAgentToolsPaginatedResponse.to_json())

# convert the object into a dict
garm_agent_tools_paginated_response_dict = garm_agent_tools_paginated_response_instance.to_dict()
# create an instance of GARMAgentToolsPaginatedResponse from a dict
garm_agent_tools_paginated_response_from_dict = GARMAgentToolsPaginatedResponse.from_dict(garm_agent_tools_paginated_response_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


