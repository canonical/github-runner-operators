# ScaleSetJobsPaginatedResponse


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**current_page** | **int** |  | [optional] 
**next_page** | **int** |  | [optional] 
**pages** | **int** |  | [optional] 
**previous_page** | **int** |  | [optional] 
**results** | [**List[ScaleSetJobsPaginatedResponseResultsInner]**](ScaleSetJobsPaginatedResponseResultsInner.md) |  | [optional] 
**total_count** | **int** |  | [optional] 

## Example

```python
from garm_client.models.scale_set_jobs_paginated_response import ScaleSetJobsPaginatedResponse

# TODO update the JSON string below
json = "{}"
# create an instance of ScaleSetJobsPaginatedResponse from a JSON string
scale_set_jobs_paginated_response_instance = ScaleSetJobsPaginatedResponse.from_json(json)
# print the JSON string representation of the object
print(ScaleSetJobsPaginatedResponse.to_json())

# convert the object into a dict
scale_set_jobs_paginated_response_dict = scale_set_jobs_paginated_response_instance.to_dict()
# create an instance of ScaleSetJobsPaginatedResponse from a dict
scale_set_jobs_paginated_response_from_dict = ScaleSetJobsPaginatedResponse.from_dict(scale_set_jobs_paginated_response_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


