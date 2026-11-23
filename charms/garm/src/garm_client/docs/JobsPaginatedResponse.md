# JobsPaginatedResponse


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**current_page** | **int** |  | [optional] 
**next_page** | **int** |  | [optional] 
**pages** | **int** |  | [optional] 
**previous_page** | **int** |  | [optional] 
**results** | [**List[JobsPaginatedResponseResultsInner]**](JobsPaginatedResponseResultsInner.md) |  | [optional] 
**total_count** | **int** |  | [optional] 

## Example

```python
from garm_client.models.jobs_paginated_response import JobsPaginatedResponse

# TODO update the JSON string below
json = "{}"
# create an instance of JobsPaginatedResponse from a JSON string
jobs_paginated_response_instance = JobsPaginatedResponse.from_json(json)
# print the JSON string representation of the object
print(JobsPaginatedResponse.to_json())

# convert the object into a dict
jobs_paginated_response_dict = jobs_paginated_response_instance.to_dict()
# create an instance of JobsPaginatedResponse from a dict
jobs_paginated_response_from_dict = JobsPaginatedResponse.from_dict(jobs_paginated_response_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


