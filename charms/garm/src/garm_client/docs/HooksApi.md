# garm_client.HooksApi

All URIs are relative to */api/v1*

Method | HTTP request | Description
------------- | ------------- | -------------
[**get_org_webhook_info**](HooksApi.md#get_org_webhook_info) | **GET** /organizations/{orgID}/webhook | Get information about the GARM installed webhook on an organization.
[**get_repo_webhook_info**](HooksApi.md#get_repo_webhook_info) | **GET** /repositories/{repoID}/webhook | Get information about the GARM installed webhook on a repository.
[**install_org_webhook**](HooksApi.md#install_org_webhook) | **POST** /organizations/{orgID}/webhook | 
[**install_repo_webhook**](HooksApi.md#install_repo_webhook) | **POST** /repositories/{repoID}/webhook | 
[**uninstall_org_webhook**](HooksApi.md#uninstall_org_webhook) | **DELETE** /organizations/{orgID}/webhook | Uninstall organization webhook.
[**uninstall_repo_webhook**](HooksApi.md#uninstall_repo_webhook) | **DELETE** /repositories/{repoID}/webhook | Uninstall organization webhook.


# **get_org_webhook_info**
> HookInfo get_org_webhook_info(org_id)

Get information about the GARM installed webhook on an organization.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.hook_info import HookInfo
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
    api_instance = garm_client.HooksApi(api_client)
    org_id = 'org_id_example' # str | Organization ID.

    try:
        # Get information about the GARM installed webhook on an organization.
        api_response = api_instance.get_org_webhook_info(org_id)
        print("The response of HooksApi->get_org_webhook_info:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling HooksApi->get_org_webhook_info: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **org_id** | **str**| Organization ID. | 

### Return type

[**HookInfo**](HookInfo.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | HookInfo |  -  |
**0** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **get_repo_webhook_info**
> HookInfo get_repo_webhook_info(repo_id)

Get information about the GARM installed webhook on a repository.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.hook_info import HookInfo
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
    api_instance = garm_client.HooksApi(api_client)
    repo_id = 'repo_id_example' # str | Repository ID.

    try:
        # Get information about the GARM installed webhook on a repository.
        api_response = api_instance.get_repo_webhook_info(repo_id)
        print("The response of HooksApi->get_repo_webhook_info:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling HooksApi->get_repo_webhook_info: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **repo_id** | **str**| Repository ID. | 

### Return type

[**HookInfo**](HookInfo.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | HookInfo |  -  |
**0** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **install_org_webhook**
> HookInfo install_org_webhook(org_id, body)

Install the GARM webhook for an organization. The secret configured on the organization will
be used to validate the requests.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.hook_info import HookInfo
from garm_client.models.install_webhook_params import InstallWebhookParams
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
    api_instance = garm_client.HooksApi(api_client)
    org_id = 'org_id_example' # str | Organization ID.
    body = garm_client.InstallWebhookParams() # InstallWebhookParams | Parameters used when creating the organization webhook.

    try:
        api_response = api_instance.install_org_webhook(org_id, body)
        print("The response of HooksApi->install_org_webhook:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling HooksApi->install_org_webhook: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **org_id** | **str**| Organization ID. | 
 **body** | [**InstallWebhookParams**](InstallWebhookParams.md)| Parameters used when creating the organization webhook. | 

### Return type

[**HookInfo**](HookInfo.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | HookInfo |  -  |
**0** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **install_repo_webhook**
> HookInfo install_repo_webhook(repo_id, body)

Install the GARM webhook for an organization. The secret configured on the organization will
be used to validate the requests.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.hook_info import HookInfo
from garm_client.models.install_webhook_params import InstallWebhookParams
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
    api_instance = garm_client.HooksApi(api_client)
    repo_id = 'repo_id_example' # str | Repository ID.
    body = garm_client.InstallWebhookParams() # InstallWebhookParams | Parameters used when creating the repository webhook.

    try:
        api_response = api_instance.install_repo_webhook(repo_id, body)
        print("The response of HooksApi->install_repo_webhook:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling HooksApi->install_repo_webhook: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **repo_id** | **str**| Repository ID. | 
 **body** | [**InstallWebhookParams**](InstallWebhookParams.md)| Parameters used when creating the repository webhook. | 

### Return type

[**HookInfo**](HookInfo.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | HookInfo |  -  |
**0** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **uninstall_org_webhook**
> APIErrorResponse uninstall_org_webhook(org_id)

Uninstall organization webhook.

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
    api_instance = garm_client.HooksApi(api_client)
    org_id = 'org_id_example' # str | Organization ID.

    try:
        # Uninstall organization webhook.
        api_response = api_instance.uninstall_org_webhook(org_id)
        print("The response of HooksApi->uninstall_org_webhook:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling HooksApi->uninstall_org_webhook: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **org_id** | **str**| Organization ID. | 

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

# **uninstall_repo_webhook**
> APIErrorResponse uninstall_repo_webhook(repo_id)

Uninstall organization webhook.

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
    api_instance = garm_client.HooksApi(api_client)
    repo_id = 'repo_id_example' # str | Repository ID.

    try:
        # Uninstall organization webhook.
        api_response = api_instance.uninstall_repo_webhook(repo_id)
        print("The response of HooksApi->uninstall_repo_webhook:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling HooksApi->uninstall_repo_webhook: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **repo_id** | **str**| Repository ID. | 

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

