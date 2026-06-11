# garm_client.RepositoriesApi

All URIs are relative to */api/v1*

Method | HTTP request | Description
------------- | ------------- | -------------
[**create_repo**](RepositoriesApi.md#create_repo) | **POST** /repositories | Create repository with the parameters given.
[**create_repo_pool**](RepositoriesApi.md#create_repo_pool) | **POST** /repositories/{repoID}/pools | Create repository pool with the parameters given.
[**create_repo_scale_set**](RepositoriesApi.md#create_repo_scale_set) | **POST** /repositories/{repoID}/scalesets | Create repository scale set with the parameters given.
[**delete_repo**](RepositoriesApi.md#delete_repo) | **DELETE** /repositories/{repoID} | Delete repository by ID.
[**delete_repo_pool**](RepositoriesApi.md#delete_repo_pool) | **DELETE** /repositories/{repoID}/pools/{poolID} | Delete repository pool by ID.
[**get_repo**](RepositoriesApi.md#get_repo) | **GET** /repositories/{repoID} | Get repository by ID.
[**get_repo_pool**](RepositoriesApi.md#get_repo_pool) | **GET** /repositories/{repoID}/pools/{poolID} | Get repository pool by ID.
[**get_repo_webhook_info**](RepositoriesApi.md#get_repo_webhook_info) | **GET** /repositories/{repoID}/webhook | Get information about the GARM installed webhook on a repository.
[**install_repo_webhook**](RepositoriesApi.md#install_repo_webhook) | **POST** /repositories/{repoID}/webhook | 
[**list_repo_instances**](RepositoriesApi.md#list_repo_instances) | **GET** /repositories/{repoID}/instances | List repository instances.
[**list_repo_pools**](RepositoriesApi.md#list_repo_pools) | **GET** /repositories/{repoID}/pools | List repository pools.
[**list_repo_scale_sets**](RepositoriesApi.md#list_repo_scale_sets) | **GET** /repositories/{repoID}/scalesets | List repository scale sets.
[**list_repos**](RepositoriesApi.md#list_repos) | **GET** /repositories | List repositories.
[**uninstall_repo_webhook**](RepositoriesApi.md#uninstall_repo_webhook) | **DELETE** /repositories/{repoID}/webhook | Uninstall organization webhook.
[**update_repo**](RepositoriesApi.md#update_repo) | **PUT** /repositories/{repoID} | Update repository with the parameters given.
[**update_repo_pool**](RepositoriesApi.md#update_repo_pool) | **PUT** /repositories/{repoID}/pools/{poolID} | Update repository pool with the parameters given.


# **create_repo**
> Repository create_repo(body)

Create repository with the parameters given.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.create_repo_params import CreateRepoParams
from garm_client.models.repository import Repository
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
    api_instance = garm_client.RepositoriesApi(api_client)
    body = garm_client.CreateRepoParams() # CreateRepoParams | Parameters used when creating the repository.

    try:
        # Create repository with the parameters given.
        api_response = api_instance.create_repo(body)
        print("The response of RepositoriesApi->create_repo:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling RepositoriesApi->create_repo: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **body** | [**CreateRepoParams**](CreateRepoParams.md)| Parameters used when creating the repository. | 

### Return type

[**Repository**](Repository.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | Repository |  -  |
**0** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **create_repo_pool**
> Pool create_repo_pool(repo_id, body)

Create repository pool with the parameters given.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.create_pool_params import CreatePoolParams
from garm_client.models.pool import Pool
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
    api_instance = garm_client.RepositoriesApi(api_client)
    repo_id = 'repo_id_example' # str | Repository ID.
    body = garm_client.CreatePoolParams() # CreatePoolParams | Parameters used when creating the repository pool.

    try:
        # Create repository pool with the parameters given.
        api_response = api_instance.create_repo_pool(repo_id, body)
        print("The response of RepositoriesApi->create_repo_pool:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling RepositoriesApi->create_repo_pool: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **repo_id** | **str**| Repository ID. | 
 **body** | [**CreatePoolParams**](CreatePoolParams.md)| Parameters used when creating the repository pool. | 

### Return type

[**Pool**](Pool.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | Pool |  -  |
**0** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **create_repo_scale_set**
> ScaleSet create_repo_scale_set(repo_id, body)

Create repository scale set with the parameters given.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.create_scale_set_params import CreateScaleSetParams
from garm_client.models.scale_set import ScaleSet
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
    api_instance = garm_client.RepositoriesApi(api_client)
    repo_id = 'repo_id_example' # str | Repository ID.
    body = garm_client.CreateScaleSetParams() # CreateScaleSetParams | Parameters used when creating the repository scale set.

    try:
        # Create repository scale set with the parameters given.
        api_response = api_instance.create_repo_scale_set(repo_id, body)
        print("The response of RepositoriesApi->create_repo_scale_set:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling RepositoriesApi->create_repo_scale_set: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **repo_id** | **str**| Repository ID. | 
 **body** | [**CreateScaleSetParams**](CreateScaleSetParams.md)| Parameters used when creating the repository scale set. | 

### Return type

[**ScaleSet**](ScaleSet.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | ScaleSet |  -  |
**0** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **delete_repo**
> APIErrorResponse delete_repo(repo_id, keep_webhook=keep_webhook)

Delete repository by ID.

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
    api_instance = garm_client.RepositoriesApi(api_client)
    repo_id = 'repo_id_example' # str | ID of the repository to delete.
    keep_webhook = True # bool | If true and a webhook is installed for this repo, it will not be removed. (optional)

    try:
        # Delete repository by ID.
        api_response = api_instance.delete_repo(repo_id, keep_webhook=keep_webhook)
        print("The response of RepositoriesApi->delete_repo:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling RepositoriesApi->delete_repo: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **repo_id** | **str**| ID of the repository to delete. | 
 **keep_webhook** | **bool**| If true and a webhook is installed for this repo, it will not be removed. | [optional] 

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

# **delete_repo_pool**
> APIErrorResponse delete_repo_pool(repo_id, pool_id)

Delete repository pool by ID.

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
    api_instance = garm_client.RepositoriesApi(api_client)
    repo_id = 'repo_id_example' # str | Repository ID.
    pool_id = 'pool_id_example' # str | ID of the repository pool to delete.

    try:
        # Delete repository pool by ID.
        api_response = api_instance.delete_repo_pool(repo_id, pool_id)
        print("The response of RepositoriesApi->delete_repo_pool:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling RepositoriesApi->delete_repo_pool: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **repo_id** | **str**| Repository ID. | 
 **pool_id** | **str**| ID of the repository pool to delete. | 

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

# **get_repo**
> Repository get_repo(repo_id)

Get repository by ID.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.repository import Repository
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
    api_instance = garm_client.RepositoriesApi(api_client)
    repo_id = 'repo_id_example' # str | ID of the repository to fetch.

    try:
        # Get repository by ID.
        api_response = api_instance.get_repo(repo_id)
        print("The response of RepositoriesApi->get_repo:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling RepositoriesApi->get_repo: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **repo_id** | **str**| ID of the repository to fetch. | 

### Return type

[**Repository**](Repository.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | Repository |  -  |
**0** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **get_repo_pool**
> Pool get_repo_pool(repo_id, pool_id)

Get repository pool by ID.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.pool import Pool
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
    api_instance = garm_client.RepositoriesApi(api_client)
    repo_id = 'repo_id_example' # str | Repository ID.
    pool_id = 'pool_id_example' # str | Pool ID.

    try:
        # Get repository pool by ID.
        api_response = api_instance.get_repo_pool(repo_id, pool_id)
        print("The response of RepositoriesApi->get_repo_pool:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling RepositoriesApi->get_repo_pool: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **repo_id** | **str**| Repository ID. | 
 **pool_id** | **str**| Pool ID. | 

### Return type

[**Pool**](Pool.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | Pool |  -  |
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
    api_instance = garm_client.RepositoriesApi(api_client)
    repo_id = 'repo_id_example' # str | Repository ID.

    try:
        # Get information about the GARM installed webhook on a repository.
        api_response = api_instance.get_repo_webhook_info(repo_id)
        print("The response of RepositoriesApi->get_repo_webhook_info:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling RepositoriesApi->get_repo_webhook_info: %s\n" % e)
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
    api_instance = garm_client.RepositoriesApi(api_client)
    repo_id = 'repo_id_example' # str | Repository ID.
    body = garm_client.InstallWebhookParams() # InstallWebhookParams | Parameters used when creating the repository webhook.

    try:
        api_response = api_instance.install_repo_webhook(repo_id, body)
        print("The response of RepositoriesApi->install_repo_webhook:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling RepositoriesApi->install_repo_webhook: %s\n" % e)
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
    api_instance = garm_client.RepositoriesApi(api_client)
    repo_id = 'repo_id_example' # str | Repository ID.

    try:
        # List repository instances.
        api_response = api_instance.list_repo_instances(repo_id)
        print("The response of RepositoriesApi->list_repo_instances:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling RepositoriesApi->list_repo_instances: %s\n" % e)
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

# **list_repo_pools**
> List[Pool] list_repo_pools(repo_id)

List repository pools.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.pool import Pool
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
    api_instance = garm_client.RepositoriesApi(api_client)
    repo_id = 'repo_id_example' # str | Repository ID.

    try:
        # List repository pools.
        api_response = api_instance.list_repo_pools(repo_id)
        print("The response of RepositoriesApi->list_repo_pools:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling RepositoriesApi->list_repo_pools: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **repo_id** | **str**| Repository ID. | 

### Return type

[**List[Pool]**](Pool.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | Pools |  -  |
**0** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **list_repo_scale_sets**
> List[ScaleSet] list_repo_scale_sets(repo_id)

List repository scale sets.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.scale_set import ScaleSet
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
    api_instance = garm_client.RepositoriesApi(api_client)
    repo_id = 'repo_id_example' # str | Repository ID.

    try:
        # List repository scale sets.
        api_response = api_instance.list_repo_scale_sets(repo_id)
        print("The response of RepositoriesApi->list_repo_scale_sets:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling RepositoriesApi->list_repo_scale_sets: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **repo_id** | **str**| Repository ID. | 

### Return type

[**List[ScaleSet]**](ScaleSet.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | ScaleSets |  -  |
**0** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **list_repos**
> List[Repository] list_repos(owner=owner, name=name, endpoint=endpoint)

List repositories.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.repository import Repository
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
    api_instance = garm_client.RepositoriesApi(api_client)
    owner = 'owner_example' # str | Exact owner name to filter by (optional)
    name = 'name_example' # str | Exact repository name to filter by (optional)
    endpoint = 'endpoint_example' # str | Exact endpoint name to filter by (optional)

    try:
        # List repositories.
        api_response = api_instance.list_repos(owner=owner, name=name, endpoint=endpoint)
        print("The response of RepositoriesApi->list_repos:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling RepositoriesApi->list_repos: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **owner** | **str**| Exact owner name to filter by | [optional] 
 **name** | **str**| Exact repository name to filter by | [optional] 
 **endpoint** | **str**| Exact endpoint name to filter by | [optional] 

### Return type

[**List[Repository]**](Repository.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | Repositories |  -  |
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
    api_instance = garm_client.RepositoriesApi(api_client)
    repo_id = 'repo_id_example' # str | Repository ID.

    try:
        # Uninstall organization webhook.
        api_response = api_instance.uninstall_repo_webhook(repo_id)
        print("The response of RepositoriesApi->uninstall_repo_webhook:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling RepositoriesApi->uninstall_repo_webhook: %s\n" % e)
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

# **update_repo**
> Repository update_repo(repo_id, body)

Update repository with the parameters given.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.repository import Repository
from garm_client.models.update_entity_params import UpdateEntityParams
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
    api_instance = garm_client.RepositoriesApi(api_client)
    repo_id = 'repo_id_example' # str | ID of the repository to update.
    body = garm_client.UpdateEntityParams() # UpdateEntityParams | Parameters used when updating the repository.

    try:
        # Update repository with the parameters given.
        api_response = api_instance.update_repo(repo_id, body)
        print("The response of RepositoriesApi->update_repo:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling RepositoriesApi->update_repo: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **repo_id** | **str**| ID of the repository to update. | 
 **body** | [**UpdateEntityParams**](UpdateEntityParams.md)| Parameters used when updating the repository. | 

### Return type

[**Repository**](Repository.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | Repository |  -  |
**0** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **update_repo_pool**
> Pool update_repo_pool(repo_id, pool_id, body)

Update repository pool with the parameters given.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.pool import Pool
from garm_client.models.update_pool_params import UpdatePoolParams
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
    api_instance = garm_client.RepositoriesApi(api_client)
    repo_id = 'repo_id_example' # str | Repository ID.
    pool_id = 'pool_id_example' # str | ID of the repository pool to update.
    body = garm_client.UpdatePoolParams() # UpdatePoolParams | Parameters used when updating the repository pool.

    try:
        # Update repository pool with the parameters given.
        api_response = api_instance.update_repo_pool(repo_id, pool_id, body)
        print("The response of RepositoriesApi->update_repo_pool:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling RepositoriesApi->update_repo_pool: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **repo_id** | **str**| Repository ID. | 
 **pool_id** | **str**| ID of the repository pool to update. | 
 **body** | [**UpdatePoolParams**](UpdatePoolParams.md)| Parameters used when updating the repository pool. | 

### Return type

[**Pool**](Pool.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | Pool |  -  |
**0** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

