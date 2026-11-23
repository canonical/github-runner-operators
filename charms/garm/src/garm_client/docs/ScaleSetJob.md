# ScaleSetJob

ScaleSetJob is the informational record of a job GitHub routed to a scale set. GitHub schedules these server side, so GARM never acts on them. They exist so users can list the jobs a scale set handled and see which runner serviced them.

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**created_at** | **datetime** |  | [optional] 
**event_name** | **str** |  | [optional] 
**finish_time** | **datetime** |  | [optional] 
**id** | **int** |  | [optional] 
**job_workflow_ref** | **str** |  | [optional] 
**name** | **str** |  | [optional] 
**queue_time** | **datetime** | Timestamps reported by GitHub for the job&#39;s routing funnel. | [optional] 
**repository_name** | **str** |  | [optional] 
**repository_owner** | **str** |  | [optional] 
**request_labels** | **List[str]** |  | [optional] 
**result** | **str** |  | [optional] 
**runner_assign_time** | **datetime** |  | [optional] 
**runner_group_name** | **str** |  | [optional] 
**runner_id** | **int** |  | [optional] 
**runner_name** | **str** |  | [optional] 
**runner_request_id** | **int** |  | [optional] 
**scaleset_assign_time** | **datetime** |  | [optional] 
**scaleset_id** | **int** | ScaleSetID is GARM&#39;s ID of the scale set that handled the job. It is zero for records migrated from older GARM versions, which never recorded the owning scale set. | [optional] 
**scaleset_job_id** | **str** | ScaleSetJobID is the job ID assigned by the GitHub actions service. | [optional] 
**status** | **str** |  | [optional] 
**updated_at** | **datetime** |  | [optional] 
**workflow_run_id** | **int** |  | [optional] 
**workflow_run_url** | **str** |  | [optional] 

## Example

```python
from garm_client.models.scale_set_job import ScaleSetJob

# TODO update the JSON string below
json = "{}"
# create an instance of ScaleSetJob from a JSON string
scale_set_job_instance = ScaleSetJob.from_json(json)
# print the JSON string representation of the object
print(ScaleSetJob.to_json())

# convert the object into a dict
scale_set_job_dict = scale_set_job_instance.to_dict()
# create an instance of ScaleSetJob from a dict
scale_set_job_from_dict = ScaleSetJob.from_dict(scale_set_job_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


