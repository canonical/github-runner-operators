# RunnerApplicationDownload

This is copied from the go-github package. It does not make sense to create a dependency on go-github just for this struct.

## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**architecture** | **str** |  | [optional] 
**download_url** | **str** |  | [optional] 
**filename** | **str** |  | [optional] 
**os** | **str** |  | [optional] 
**sha256_checksum** | **str** |  | [optional] 
**temp_download_token** | **str** |  | [optional] 

## Example

```python
from garm_client.models.runner_application_download import RunnerApplicationDownload

# TODO update the JSON string below
json = "{}"
# create an instance of RunnerApplicationDownload from a JSON string
runner_application_download_instance = RunnerApplicationDownload.from_json(json)
# print the JSON string representation of the object
print(RunnerApplicationDownload.to_json())

# convert the object into a dict
runner_application_download_dict = runner_application_download_instance.to_dict()
# create an instance of RunnerApplicationDownload from a dict
runner_application_download_from_dict = RunnerApplicationDownload.from_dict(runner_application_download_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


