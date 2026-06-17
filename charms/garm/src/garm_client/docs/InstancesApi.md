# garm_client.InstancesApi

All URIs are relative to */api/v1*

Method | HTTP request | Description
------------- | ------------- | -------------
[**delete_instance**](InstancesApi.md#delete_instance) | **DELETE** /instances/{instanceName} | Delete runner instance by name.
[**get_instance**](InstancesApi.md#get_instance) | **GET** /instances/{instanceName} | Get runner instance by name.
[**list_enterprise_instances**](InstancesApi.md#list_enterprise_instances) | **GET** /enterprises/{enterpriseID}/instances | List enterprise instances.
[**list_instances**](InstancesApi.md#list_instances) | **GET** /instances | Get all runners&#39; instances.
[**list_org_instances**](InstancesApi.md#list_org_instances) | **GET** /organizations/{orgID}/instances | List organization instances.
[**list_pool_instances**](InstancesApi.md#list_pool_instances) | **GET** /pools/{poolID}/instances | List runner instances in a pool.
[**list_repo_instances**](InstancesApi.md#list_repo_instances) | **GET** /repositories/{repoID}/instances | List repository instances.
[**list_scale_set_instances**](InstancesApi.md#list_scale_set_instances) | **GET** /scalesets/{scalesetID}/instances | List runner instances in a scale set.


# **delete_instance**
> APIErrorResponse delete_instance(instance_name, force_remove=force_remove, bypass_gh_unauthorized=bypass_gh_unauthorized)

Delete runner instance by name.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.api_error_response import APIErrorResponse
from garm_client.rest import ApiException
from pprint import pprint

# Defining the host is optional and defaults to /api/v1
# See configuration.py for a list of all supported configuration parameters.
configuration = garm_client.Configuration(
    host = "/api/v1"
)

# The client must configure the authentication and authorization parameters
# in accordance with the API server security policy.
# Examples for each auth method are provided below, use the example that
# satisfies your auth use case.

# Configure API key authorization: Bearer
configuration.api_key['Bearer'] = os.environ["API_KEY"]

# Uncomment below to setup prefix (e.g. Bearer) for API key, if needed
# configuration.api_key_prefix['Bearer'] = 'Bearer'

# Enter a context with an instance of the API client
with garm_client.ApiClient(configuration) as api_client:
    # Create an instance of the API class
    api_instance = garm_client.InstancesApi(api_client)
    instance_name = 'instance_name_example' # str | Runner instance name.
    force_remove = True # bool | If true GARM will ignore any provider error when removing the runner and will continue to remove the runner from github and the GARM database. (optional)
    bypass_gh_unauthorized = True # bool | If true GARM will ignore unauthorized errors returned by GitHub when removing a runner. This is useful if you want to clean up runners and your credentials have expired. (optional)

    try:
        # Delete runner instance by name.
        api_response = api_instance.delete_instance(instance_name, force_remove=force_remove, bypass_gh_unauthorized=bypass_gh_unauthorized)
        print("The response of InstancesApi->delete_instance:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling InstancesApi->delete_instance: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **instance_name** | **str**| Runner instance name. | 
 **force_remove** | **bool**| If true GARM will ignore any provider error when removing the runner and will continue to remove the runner from github and the GARM database. | [optional] 
 **bypass_gh_unauthorized** | **bool**| If true GARM will ignore unauthorized errors returned by GitHub when removing a runner. This is useful if you want to clean up runners and your credentials have expired. | [optional] 

### Return type

[**APIErrorResponse**](APIErrorResponse.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**0** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **get_instance**
> Instance get_instance(instance_name)

Get runner instance by name.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.instance import Instance
from garm_client.rest import ApiException
from pprint import pprint

# Defining the host is optional and defaults to /api/v1
# See configuration.py for a list of all supported configuration parameters.
configuration = garm_client.Configuration(
    host = "/api/v1"
)

# The client must configure the authentication and authorization parameters
# in accordance with the API server security policy.
# Examples for each auth method are provided below, use the example that
# satisfies your auth use case.

# Configure API key authorization: Bearer
configuration.api_key['Bearer'] = os.environ["API_KEY"]

# Uncomment below to setup prefix (e.g. Bearer) for API key, if needed
# configuration.api_key_prefix['Bearer'] = 'Bearer'

# Enter a context with an instance of the API client
with garm_client.ApiClient(configuration) as api_client:
    # Create an instance of the API class
    api_instance = garm_client.InstancesApi(api_client)
    instance_name = 'instance_name_example' # str | Runner instance name.

    try:
        # Get runner instance by name.
        api_response = api_instance.get_instance(instance_name)
        print("The response of InstancesApi->get_instance:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling InstancesApi->get_instance: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **instance_name** | **str**| Runner instance name. | 

### Return type

[**Instance**](Instance.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | Instance |  -  |
**0** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **list_enterprise_instances**
> List[Instance] list_enterprise_instances(enterprise_id)

List enterprise instances.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.instance import Instance
from garm_client.rest import ApiException
from pprint import pprint

# Defining the host is optional and defaults to /api/v1
# See configuration.py for a list of all supported configuration parameters.
configuration = garm_client.Configuration(
    host = "/api/v1"
)

# The client must configure the authentication and authorization parameters
# in accordance with the API server security policy.
# Examples for each auth method are provided below, use the example that
# satisfies your auth use case.

# Configure API key authorization: Bearer
configuration.api_key['Bearer'] = os.environ["API_KEY"]

# Uncomment below to setup prefix (e.g. Bearer) for API key, if needed
# configuration.api_key_prefix['Bearer'] = 'Bearer'

# Enter a context with an instance of the API client
with garm_client.ApiClient(configuration) as api_client:
    # Create an instance of the API class
    api_instance = garm_client.InstancesApi(api_client)
    enterprise_id = 'enterprise_id_example' # str | Enterprise ID.

    try:
        # List enterprise instances.
        api_response = api_instance.list_enterprise_instances(enterprise_id)
        print("The response of InstancesApi->list_enterprise_instances:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling InstancesApi->list_enterprise_instances: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **enterprise_id** | **str**| Enterprise ID. | 

### Return type

[**List[Instance]**](Instance.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | Instances |  -  |
**0** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **list_instances**
> List[Instance] list_instances()

Get all runners' instances.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.instance import Instance
from garm_client.rest import ApiException
from pprint import pprint

# Defining the host is optional and defaults to /api/v1
# See configuration.py for a list of all supported configuration parameters.
configuration = garm_client.Configuration(
    host = "/api/v1"
)

# The client must configure the authentication and authorization parameters
# in accordance with the API server security policy.
# Examples for each auth method are provided below, use the example that
# satisfies your auth use case.

# Configure API key authorization: Bearer
configuration.api_key['Bearer'] = os.environ["API_KEY"]

# Uncomment below to setup prefix (e.g. Bearer) for API key, if needed
# configuration.api_key_prefix['Bearer'] = 'Bearer'

# Enter a context with an instance of the API client
with garm_client.ApiClient(configuration) as api_client:
    # Create an instance of the API class
    api_instance = garm_client.InstancesApi(api_client)

    try:
        # Get all runners' instances.
        api_response = api_instance.list_instances()
        print("The response of InstancesApi->list_instances:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling InstancesApi->list_instances: %s\n" % e)
```



### Parameters

This endpoint does not need any parameter.

### Return type

[**List[Instance]**](Instance.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | Instances |  -  |
**0** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **list_org_instances**
> List[Instance] list_org_instances(org_id)

List organization instances.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.instance import Instance
from garm_client.rest import ApiException
from pprint import pprint

# Defining the host is optional and defaults to /api/v1
# See configuration.py for a list of all supported configuration parameters.
configuration = garm_client.Configuration(
    host = "/api/v1"
)

# The client must configure the authentication and authorization parameters
# in accordance with the API server security policy.
# Examples for each auth method are provided below, use the example that
# satisfies your auth use case.

# Configure API key authorization: Bearer
configuration.api_key['Bearer'] = os.environ["API_KEY"]

# Uncomment below to setup prefix (e.g. Bearer) for API key, if needed
# configuration.api_key_prefix['Bearer'] = 'Bearer'

# Enter a context with an instance of the API client
with garm_client.ApiClient(configuration) as api_client:
    # Create an instance of the API class
    api_instance = garm_client.InstancesApi(api_client)
    org_id = 'org_id_example' # str | Organization ID.

    try:
        # List organization instances.
        api_response = api_instance.list_org_instances(org_id)
        print("The response of InstancesApi->list_org_instances:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling InstancesApi->list_org_instances: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **org_id** | **str**| Organization ID. | 

### Return type

[**List[Instance]**](Instance.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | Instances |  -  |
**0** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **list_pool_instances**
> List[Instance] list_pool_instances(pool_id, outdated_only=outdated_only)

List runner instances in a pool.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.instance import Instance
from garm_client.rest import ApiException
from pprint import pprint

# Defining the host is optional and defaults to /api/v1
# See configuration.py for a list of all supported configuration parameters.
configuration = garm_client.Configuration(
    host = "/api/v1"
)

# The client must configure the authentication and authorization parameters
# in accordance with the API server security policy.
# Examples for each auth method are provided below, use the example that
# satisfies your auth use case.

# Configure API key authorization: Bearer
configuration.api_key['Bearer'] = os.environ["API_KEY"]

# Uncomment below to setup prefix (e.g. Bearer) for API key, if needed
# configuration.api_key_prefix['Bearer'] = 'Bearer'

# Enter a context with an instance of the API client
with garm_client.ApiClient(configuration) as api_client:
    # Create an instance of the API class
    api_instance = garm_client.InstancesApi(api_client)
    pool_id = 'pool_id_example' # str | Runner pool ID.
    outdated_only = True # bool | List only instances that were created prior to a pool update that changed a setting which influences how instances are created (image, flavor, runner group, etc). (optional)

    try:
        # List runner instances in a pool.
        api_response = api_instance.list_pool_instances(pool_id, outdated_only=outdated_only)
        print("The response of InstancesApi->list_pool_instances:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling InstancesApi->list_pool_instances: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **pool_id** | **str**| Runner pool ID. | 
 **outdated_only** | **bool**| List only instances that were created prior to a pool update that changed a setting which influences how instances are created (image, flavor, runner group, etc). | [optional] 

### Return type

[**List[Instance]**](Instance.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | Instances |  -  |
**0** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **list_repo_instances**
> List[Instance] list_repo_instances(repo_id)

List repository instances.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.instance import Instance
from garm_client.rest import ApiException
from pprint import pprint

# Defining the host is optional and defaults to /api/v1
# See configuration.py for a list of all supported configuration parameters.
configuration = garm_client.Configuration(
    host = "/api/v1"
)

# The client must configure the authentication and authorization parameters
# in accordance with the API server security policy.
# Examples for each auth method are provided below, use the example that
# satisfies your auth use case.

# Configure API key authorization: Bearer
configuration.api_key['Bearer'] = os.environ["API_KEY"]

# Uncomment below to setup prefix (e.g. Bearer) for API key, if needed
# configuration.api_key_prefix['Bearer'] = 'Bearer'

# Enter a context with an instance of the API client
with garm_client.ApiClient(configuration) as api_client:
    # Create an instance of the API class
    api_instance = garm_client.InstancesApi(api_client)
    repo_id = 'repo_id_example' # str | Repository ID.

    try:
        # List repository instances.
        api_response = api_instance.list_repo_instances(repo_id)
        print("The response of InstancesApi->list_repo_instances:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling InstancesApi->list_repo_instances: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **repo_id** | **str**| Repository ID. | 

### Return type

[**List[Instance]**](Instance.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | Instances |  -  |
**0** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **list_scale_set_instances**
> List[Instance] list_scale_set_instances(scaleset_id, outdated_only=outdated_only)

List runner instances in a scale set.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.instance import Instance
from garm_client.rest import ApiException
from pprint import pprint

# Defining the host is optional and defaults to /api/v1
# See configuration.py for a list of all supported configuration parameters.
configuration = garm_client.Configuration(
    host = "/api/v1"
)

# The client must configure the authentication and authorization parameters
# in accordance with the API server security policy.
# Examples for each auth method are provided below, use the example that
# satisfies your auth use case.

# Configure API key authorization: Bearer
configuration.api_key['Bearer'] = os.environ["API_KEY"]

# Uncomment below to setup prefix (e.g. Bearer) for API key, if needed
# configuration.api_key_prefix['Bearer'] = 'Bearer'

# Enter a context with an instance of the API client
with garm_client.ApiClient(configuration) as api_client:
    # Create an instance of the API class
    api_instance = garm_client.InstancesApi(api_client)
    scaleset_id = 'scaleset_id_example' # str | Runner scale set ID.
    outdated_only = True # bool | List only instances that were created prior to a scaleset update that changed a setting which influences how instances are created (image, flavor, runner group, etc). (optional)

    try:
        # List runner instances in a scale set.
        api_response = api_instance.list_scale_set_instances(scaleset_id, outdated_only=outdated_only)
        print("The response of InstancesApi->list_scale_set_instances:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling InstancesApi->list_scale_set_instances: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **scaleset_id** | **str**| Runner scale set ID. | 
 **outdated_only** | **bool**| List only instances that were created prior to a scaleset update that changed a setting which influences how instances are created (image, flavor, runner group, etc). | [optional] 

### Return type

[**List[Instance]**](Instance.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | Instances |  -  |
**0** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

