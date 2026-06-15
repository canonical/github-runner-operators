# ControllerInfo


## Properties

Name | Type | Description | Notes
------------ | ------------- | ------------- | -------------
**agent_url** | **str** | AgentURL is the URL where the GARM agent will connect. If set behind a reverse proxy, this URL must be configured to allow websocket connections. | [optional] 
**ca_cert_bundle** | **List[int]** | CACertBundle holds a certificate bundle meant to validate the certificate used by GARM itself. This can be just the root certificate that can validate the GARM TLS certificate, a chain or multiple root CAs. | [optional] 
**cached_garm_agent_release_fetched_at** | **datetime** | CachedGARMAgentReleaseFetchedAt is the timestamp when the release data was last fetched from GARMAgentReleasesURL | [optional] 
**callback_url** | **str** | CallbackURL is the URL where instances can send updates back to the controller. This URL is used by instances to send status updates back to the controller. The URL itself may be made available to instances via a reverse proxy or a load balancer. That means that the user is responsible for telling GARM what the public URL is, by setting this field. | [optional] 
**controller_id** | **UUID** | ControllerID is the unique ID of this controller. This ID gets generated automatically on controller init. | [optional] 
**controller_webhook_url** | **str** | ControllerWebhookURL is the controller specific URL where webhooks will be received. This field holds the WebhookURL defined above to which we append the ControllerID. Functionally it is the same as WebhookURL, but it allows us to safely manage webhooks from GARM without accidentally removing webhooks from other services or GARM controllers. | [optional] 
**enable_agent_tools_sync** | **bool** | SyncGARMAgentTools enables or disables automatic sync of garm-agent tools. | [optional] 
**garm_agent_releases_url** | **str** | GARMAgentReleasesURL is the URL from where GARM can fetch garm-agent binaries. This URL must have an API response compatible with the github releases API. The default value for this field is: https://api.github.com/repos/cloudbase/garm-agent/releases | [optional] 
**hostname** | **str** | Hostname is the hostname of the machine that runs this controller. In the future, this field will be migrated to a separate table that will keep track of each the controller nodes that are part of a cluster. This will happen when we implement controller scale-out capability. | [optional] 
**metadata_url** | **str** | MetadataURL is the public metadata URL of the GARM instance. This URL is used by instances to fetch information they need to set themselves up. The URL itself may be made available to runners via a reverse proxy or a load balancer. That means that the user is responsible for telling GARM what the public URL is, by setting this field. | [optional] 
**minimum_job_age_backoff** | **int** | MinimumJobAgeBackoff is the minimum time in seconds that a job must be in queued state before GARM will attempt to allocate a runner for it. When set to a non zero value, GARM will ignore the job until the job&#39;s age is greater than this value. When using the min_idle_runners feature of a pool, this gives enough time for potential idle runners to pick up the job before GARM attempts to allocate a new runner, thus avoiding the need to potentially scale down runners later. | [optional] 
**version** | **str** | Version is the version of the GARM controller. | [optional] 
**webhook_url** | **str** | WebhookURL is the base URL where the controller will receive webhooks from github. When webhook management is used, this URL is used as a base to which the controller UUID is appended and which will receive the webhooks. The URL itself may be made available to instances via a reverse proxy or a load balancer. That means that the user is responsible for telling GARM what the public URL is, by setting this field. | [optional] 

## Example

```python
from garm_client.models.controller_info import ControllerInfo

# TODO update the JSON string below
json = "{}"
# create an instance of ControllerInfo from a JSON string
controller_info_instance = ControllerInfo.from_json(json)
# print the JSON string representation of the object
print(ControllerInfo.to_json())

# convert the object into a dict
controller_info_dict = controller_info_instance.to_dict()
# create an instance of ControllerInfo from a dict
controller_info_from_dict = ControllerInfo.from_dict(controller_info_dict)
```
[[Back to Model list]](../README.md#documentation-for-models) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to README]](../README.md)


