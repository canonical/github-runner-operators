# garm_client.PoolsApi

All URIs are relative to */api/v1*

Method | HTTP request | Description
------------- | ------------- | -------------
[**create_enterprise_pool**](PoolsApi.md#create_enterprise_pool) | **POST** /enterprises/{enterpriseID}/pools | Create enterprise pool with the parameters given.
[**create_org_pool**](PoolsApi.md#create_org_pool) | **POST** /organizations/{orgID}/pools | Create organization pool with the parameters given.
[**create_repo_pool**](PoolsApi.md#create_repo_pool) | **POST** /repositories/{repoID}/pools | Create repository pool with the parameters given.
[**delete_enterprise_pool**](PoolsApi.md#delete_enterprise_pool) | **DELETE** /enterprises/{enterpriseID}/pools/{poolID} | Delete enterprise pool by ID.
[**delete_org_pool**](PoolsApi.md#delete_org_pool) | **DELETE** /organizations/{orgID}/pools/{poolID} | Delete organization pool by ID.
[**delete_pool**](PoolsApi.md#delete_pool) | **DELETE** /pools/{poolID} | Delete pool by ID.
[**delete_repo_pool**](PoolsApi.md#delete_repo_pool) | **DELETE** /repositories/{repoID}/pools/{poolID} | Delete repository pool by ID.
[**get_enterprise_pool**](PoolsApi.md#get_enterprise_pool) | **GET** /enterprises/{enterpriseID}/pools/{poolID} | Get enterprise pool by ID.
[**get_org_pool**](PoolsApi.md#get_org_pool) | **GET** /organizations/{orgID}/pools/{poolID} | Get organization pool by ID.
[**get_pool**](PoolsApi.md#get_pool) | **GET** /pools/{poolID} | Get pool by ID.
[**get_repo_pool**](PoolsApi.md#get_repo_pool) | **GET** /repositories/{repoID}/pools/{poolID} | Get repository pool by ID.
[**list_enterprise_pools**](PoolsApi.md#list_enterprise_pools) | **GET** /enterprises/{enterpriseID}/pools | List enterprise pools.
[**list_org_pools**](PoolsApi.md#list_org_pools) | **GET** /organizations/{orgID}/pools | List organization pools.
[**list_pools**](PoolsApi.md#list_pools) | **GET** /pools | List all pools.
[**list_repo_pools**](PoolsApi.md#list_repo_pools) | **GET** /repositories/{repoID}/pools | List repository pools.
[**update_enterprise_pool**](PoolsApi.md#update_enterprise_pool) | **PUT** /enterprises/{enterpriseID}/pools/{poolID} | Update enterprise pool with the parameters given.
[**update_org_pool**](PoolsApi.md#update_org_pool) | **PUT** /organizations/{orgID}/pools/{poolID} | Update organization pool with the parameters given.
[**update_pool**](PoolsApi.md#update_pool) | **PUT** /pools/{poolID} | Update pool by ID.
[**update_repo_pool**](PoolsApi.md#update_repo_pool) | **PUT** /repositories/{repoID}/pools/{poolID} | Update repository pool with the parameters given.


# **create_enterprise_pool**
> Pool create_enterprise_pool(enterprise_id, body)

Create enterprise pool with the parameters given.

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
    api_instance = garm_client.PoolsApi(api_client)
    enterprise_id = 'enterprise_id_example' # str | Enterprise ID.
    body = garm_client.CreatePoolParams() # CreatePoolParams | Parameters used when creating the enterprise pool.

    try:
        # Create enterprise pool with the parameters given.
        api_response = api_instance.create_enterprise_pool(enterprise_id, body)
        print("The response of PoolsApi->create_enterprise_pool:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling PoolsApi->create_enterprise_pool: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **enterprise_id** | **str**| Enterprise ID. | 
 **body** | [**CreatePoolParams**](CreatePoolParams.md)| Parameters used when creating the enterprise pool. | 

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

# **create_org_pool**
> Pool create_org_pool(org_id, body)

Create organization pool with the parameters given.

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
    api_instance = garm_client.PoolsApi(api_client)
    org_id = 'org_id_example' # str | Organization ID.
    body = garm_client.CreatePoolParams() # CreatePoolParams | Parameters used when creating the organization pool.

    try:
        # Create organization pool with the parameters given.
        api_response = api_instance.create_org_pool(org_id, body)
        print("The response of PoolsApi->create_org_pool:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling PoolsApi->create_org_pool: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **org_id** | **str**| Organization ID. | 
 **body** | [**CreatePoolParams**](CreatePoolParams.md)| Parameters used when creating the organization pool. | 

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
    api_instance = garm_client.PoolsApi(api_client)
    repo_id = 'repo_id_example' # str | Repository ID.
    body = garm_client.CreatePoolParams() # CreatePoolParams | Parameters used when creating the repository pool.

    try:
        # Create repository pool with the parameters given.
        api_response = api_instance.create_repo_pool(repo_id, body)
        print("The response of PoolsApi->create_repo_pool:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling PoolsApi->create_repo_pool: %s\n" % e)
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

# **delete_enterprise_pool**
> APIErrorResponse delete_enterprise_pool(enterprise_id, pool_id)

Delete enterprise pool by ID.

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
    api_instance = garm_client.PoolsApi(api_client)
    enterprise_id = 'enterprise_id_example' # str | Enterprise ID.
    pool_id = 'pool_id_example' # str | ID of the enterprise pool to delete.

    try:
        # Delete enterprise pool by ID.
        api_response = api_instance.delete_enterprise_pool(enterprise_id, pool_id)
        print("The response of PoolsApi->delete_enterprise_pool:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling PoolsApi->delete_enterprise_pool: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **enterprise_id** | **str**| Enterprise ID. | 
 **pool_id** | **str**| ID of the enterprise pool to delete. | 

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

# **delete_org_pool**
> APIErrorResponse delete_org_pool(org_id, pool_id)

Delete organization pool by ID.

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
    api_instance = garm_client.PoolsApi(api_client)
    org_id = 'org_id_example' # str | Organization ID.
    pool_id = 'pool_id_example' # str | ID of the organization pool to delete.

    try:
        # Delete organization pool by ID.
        api_response = api_instance.delete_org_pool(org_id, pool_id)
        print("The response of PoolsApi->delete_org_pool:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling PoolsApi->delete_org_pool: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **org_id** | **str**| Organization ID. | 
 **pool_id** | **str**| ID of the organization pool to delete. | 

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

# **delete_pool**
> APIErrorResponse delete_pool(pool_id)

Delete pool by ID.

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
    api_instance = garm_client.PoolsApi(api_client)
    pool_id = 'pool_id_example' # str | ID of the pool to delete.

    try:
        # Delete pool by ID.
        api_response = api_instance.delete_pool(pool_id)
        print("The response of PoolsApi->delete_pool:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling PoolsApi->delete_pool: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **pool_id** | **str**| ID of the pool to delete. | 

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
    api_instance = garm_client.PoolsApi(api_client)
    repo_id = 'repo_id_example' # str | Repository ID.
    pool_id = 'pool_id_example' # str | ID of the repository pool to delete.

    try:
        # Delete repository pool by ID.
        api_response = api_instance.delete_repo_pool(repo_id, pool_id)
        print("The response of PoolsApi->delete_repo_pool:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling PoolsApi->delete_repo_pool: %s\n" % e)
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

# **get_enterprise_pool**
> Pool get_enterprise_pool(enterprise_id, pool_id)

Get enterprise pool by ID.

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
    api_instance = garm_client.PoolsApi(api_client)
    enterprise_id = 'enterprise_id_example' # str | Enterprise ID.
    pool_id = 'pool_id_example' # str | Pool ID.

    try:
        # Get enterprise pool by ID.
        api_response = api_instance.get_enterprise_pool(enterprise_id, pool_id)
        print("The response of PoolsApi->get_enterprise_pool:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling PoolsApi->get_enterprise_pool: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **enterprise_id** | **str**| Enterprise ID. | 
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

# **get_org_pool**
> Pool get_org_pool(org_id, pool_id)

Get organization pool by ID.

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
    api_instance = garm_client.PoolsApi(api_client)
    org_id = 'org_id_example' # str | Organization ID.
    pool_id = 'pool_id_example' # str | Pool ID.

    try:
        # Get organization pool by ID.
        api_response = api_instance.get_org_pool(org_id, pool_id)
        print("The response of PoolsApi->get_org_pool:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling PoolsApi->get_org_pool: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **org_id** | **str**| Organization ID. | 
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

# **get_pool**
> Pool get_pool(pool_id)

Get pool by ID.

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
    api_instance = garm_client.PoolsApi(api_client)
    pool_id = 'pool_id_example' # str | ID of the pool to fetch.

    try:
        # Get pool by ID.
        api_response = api_instance.get_pool(pool_id)
        print("The response of PoolsApi->get_pool:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling PoolsApi->get_pool: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **pool_id** | **str**| ID of the pool to fetch. | 

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
    api_instance = garm_client.PoolsApi(api_client)
    repo_id = 'repo_id_example' # str | Repository ID.
    pool_id = 'pool_id_example' # str | Pool ID.

    try:
        # Get repository pool by ID.
        api_response = api_instance.get_repo_pool(repo_id, pool_id)
        print("The response of PoolsApi->get_repo_pool:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling PoolsApi->get_repo_pool: %s\n" % e)
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

# **list_enterprise_pools**
> List[Pool] list_enterprise_pools(enterprise_id)

List enterprise pools.

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
    api_instance = garm_client.PoolsApi(api_client)
    enterprise_id = 'enterprise_id_example' # str | Enterprise ID.

    try:
        # List enterprise pools.
        api_response = api_instance.list_enterprise_pools(enterprise_id)
        print("The response of PoolsApi->list_enterprise_pools:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling PoolsApi->list_enterprise_pools: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **enterprise_id** | **str**| Enterprise ID. | 

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

# **list_org_pools**
> List[Pool] list_org_pools(org_id)

List organization pools.

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
    api_instance = garm_client.PoolsApi(api_client)
    org_id = 'org_id_example' # str | Organization ID.

    try:
        # List organization pools.
        api_response = api_instance.list_org_pools(org_id)
        print("The response of PoolsApi->list_org_pools:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling PoolsApi->list_org_pools: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **org_id** | **str**| Organization ID. | 

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

# **list_pools**
> List[Pool] list_pools()

List all pools.

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
    api_instance = garm_client.PoolsApi(api_client)

    try:
        # List all pools.
        api_response = api_instance.list_pools()
        print("The response of PoolsApi->list_pools:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling PoolsApi->list_pools: %s\n" % e)
```



### Parameters

This endpoint does not need any parameter.

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
    api_instance = garm_client.PoolsApi(api_client)
    repo_id = 'repo_id_example' # str | Repository ID.

    try:
        # List repository pools.
        api_response = api_instance.list_repo_pools(repo_id)
        print("The response of PoolsApi->list_repo_pools:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling PoolsApi->list_repo_pools: %s\n" % e)
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

# **update_enterprise_pool**
> Pool update_enterprise_pool(enterprise_id, pool_id, body)

Update enterprise pool with the parameters given.

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
    api_instance = garm_client.PoolsApi(api_client)
    enterprise_id = 'enterprise_id_example' # str | Enterprise ID.
    pool_id = 'pool_id_example' # str | ID of the enterprise pool to update.
    body = garm_client.UpdatePoolParams() # UpdatePoolParams | Parameters used when updating the enterprise pool.

    try:
        # Update enterprise pool with the parameters given.
        api_response = api_instance.update_enterprise_pool(enterprise_id, pool_id, body)
        print("The response of PoolsApi->update_enterprise_pool:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling PoolsApi->update_enterprise_pool: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **enterprise_id** | **str**| Enterprise ID. | 
 **pool_id** | **str**| ID of the enterprise pool to update. | 
 **body** | [**UpdatePoolParams**](UpdatePoolParams.md)| Parameters used when updating the enterprise pool. | 

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

# **update_org_pool**
> Pool update_org_pool(org_id, pool_id, body)

Update organization pool with the parameters given.

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
    api_instance = garm_client.PoolsApi(api_client)
    org_id = 'org_id_example' # str | Organization ID.
    pool_id = 'pool_id_example' # str | ID of the organization pool to update.
    body = garm_client.UpdatePoolParams() # UpdatePoolParams | Parameters used when updating the organization pool.

    try:
        # Update organization pool with the parameters given.
        api_response = api_instance.update_org_pool(org_id, pool_id, body)
        print("The response of PoolsApi->update_org_pool:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling PoolsApi->update_org_pool: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **org_id** | **str**| Organization ID. | 
 **pool_id** | **str**| ID of the organization pool to update. | 
 **body** | [**UpdatePoolParams**](UpdatePoolParams.md)| Parameters used when updating the organization pool. | 

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

# **update_pool**
> Pool update_pool(pool_id, body)

Update pool by ID.

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
    api_instance = garm_client.PoolsApi(api_client)
    pool_id = 'pool_id_example' # str | ID of the pool to update.
    body = garm_client.UpdatePoolParams() # UpdatePoolParams | Parameters to update the pool with.

    try:
        # Update pool by ID.
        api_response = api_instance.update_pool(pool_id, body)
        print("The response of PoolsApi->update_pool:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling PoolsApi->update_pool: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **pool_id** | **str**| ID of the pool to update. | 
 **body** | [**UpdatePoolParams**](UpdatePoolParams.md)| Parameters to update the pool with. | 

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
    api_instance = garm_client.PoolsApi(api_client)
    repo_id = 'repo_id_example' # str | Repository ID.
    pool_id = 'pool_id_example' # str | ID of the repository pool to update.
    body = garm_client.UpdatePoolParams() # UpdatePoolParams | Parameters used when updating the repository pool.

    try:
        # Update repository pool with the parameters given.
        api_response = api_instance.update_repo_pool(repo_id, pool_id, body)
        print("The response of PoolsApi->update_repo_pool:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling PoolsApi->update_repo_pool: %s\n" % e)
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

