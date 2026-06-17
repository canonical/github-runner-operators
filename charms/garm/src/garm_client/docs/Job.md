# Job


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**action** | **str** | Action is the specific activity that triggered the event. | [optional] 
**completed_at** | **datetime** |  | [optional] 
**conclusion** | **str** | Conclusion is the outcome of the job. Possible values: \&quot;success\&quot;, \&quot;failure\&quot;, \&quot;neutral\&quot;, \&quot;cancelled\&quot;, \&quot;skipped\&quot;, \&quot;timed_out\&quot;, \&quot;action_required\&quot; | [optional] 
**created_at** | **datetime** |  | [optional] 
**enterprise_id** | **UUID** |  | [optional] 
**id** | **int** | ID is the ID of the job. | [optional] 
**labels** | **List[str]** |  | [optional] 
**locked_by** | **UUID** |  | [optional] 
**name** | **str** | Name is the name if the job that was triggered. | [optional] 
**org_id** | **UUID** |  | [optional] 
**repo_id** | **UUID** | The entity that received the hook.  Webhooks may be configured on the repo, the org and/or the enterprise. If we only configure a repo to use garm, we&#39;ll only ever receive a webhook from the repo. But if we configure the parent org of the repo and the parent enterprise of the org to use garm, a webhook will be sent for each entity type, in response to one workflow event. Thus, we will get 3 webhooks with the same run_id and job id. Record all involved entities in the same job if we have them configured in garm. | [optional] 
**repository_name** | **str** | repository in which the job was triggered. | [optional] 
**repository_owner** | **str** |  | [optional] 
**run_id** | **int** | RunID is the ID of the workflow run. A run may have multiple jobs. | [optional] 
**runner_group_id** | **int** |  | [optional] 
**runner_group_name** | **str** |  | [optional] 
**runner_id** | **int** |  | [optional] 
**runner_name** | **str** |  | [optional] 
**scaleset_job_id** | **str** | ScaleSetJobID is the job ID when generated for a scale set. | [optional] 
**started_at** | **datetime** |  | [optional] 
**status** | **str** | Status is the phase of the lifecycle that the job is currently in. \&quot;queued\&quot;, \&quot;in_progress\&quot; and \&quot;completed\&quot;. | [optional] 
**updated_at** | **datetime** |  | [optional] 
**workflow_job_id** | **int** |  | [optional] 
**workflow_run_url** | **str** |  | [optional] 

## Example

```python
from garm_client.models.job import Job

# TODO update the JSON string below
json = "{}"
# create an instance of Job from a JSON string
job_instance = Job.from_json(json)
# print the JSON string representation of the object
print(Job.to_json())

# convert the object into a dict
job_dict = job_instance.to_dict()
# create an instance of Job from a dict
job_from_dict = Job.from_dict(job_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


