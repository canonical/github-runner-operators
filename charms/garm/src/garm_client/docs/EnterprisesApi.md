# garm_client.EnterprisesApi

All URIs are relative to */api/v1*

Method | HTTP request | Description
------------- | ------------- | -------------
[**create_enterprise**](EnterprisesApi.md#create_enterprise) | **POST** /enterprises | Create enterprise with the given parameters.
[**create_enterprise_pool**](EnterprisesApi.md#create_enterprise_pool) | **POST** /enterprises/{enterpriseID}/pools | Create enterprise pool with the parameters given.
[**create_enterprise_scale_set**](EnterprisesApi.md#create_enterprise_scale_set) | **POST** /enterprises/{enterpriseID}/scalesets | Create enterprise pool with the parameters given.
[**delete_enterprise**](EnterprisesApi.md#delete_enterprise) | **DELETE** /enterprises/{enterpriseID} | Delete enterprise by ID.
[**delete_enterprise_pool**](EnterprisesApi.md#delete_enterprise_pool) | **DELETE** /enterprises/{enterpriseID}/pools/{poolID} | Delete enterprise pool by ID.
[**get_enterprise**](EnterprisesApi.md#get_enterprise) | **GET** /enterprises/{enterpriseID} | Get enterprise by ID.
[**get_enterprise_pool**](EnterprisesApi.md#get_enterprise_pool) | **GET** /enterprises/{enterpriseID}/pools/{poolID} | Get enterprise pool by ID.
[**list_enterprise_instances**](EnterprisesApi.md#list_enterprise_instances) | **GET** /enterprises/{enterpriseID}/instances | List enterprise instances.
[**list_enterprise_pools**](EnterprisesApi.md#list_enterprise_pools) | **GET** /enterprises/{enterpriseID}/pools | List enterprise pools.
[**list_enterprise_scale_sets**](EnterprisesApi.md#list_enterprise_scale_sets) | **GET** /enterprises/{enterpriseID}/scalesets | List enterprise scale sets.
[**list_enterprises**](EnterprisesApi.md#list_enterprises) | **GET** /enterprises | List all enterprises.
[**update_enterprise**](EnterprisesApi.md#update_enterprise) | **PUT** /enterprises/{enterpriseID} | Update enterprise with the given parameters.
[**update_enterprise_pool**](EnterprisesApi.md#update_enterprise_pool) | **PUT** /enterprises/{enterpriseID}/pools/{poolID} | Update enterprise pool with the parameters given.


# **create_enterprise**
> Enterprise create_enterprise(body)

Create enterprise with the given parameters.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.create_enterprise_params import CreateEnterpriseParams
from garm_client.models.enterprise import Enterprise
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
    api_instance = garm_client.EnterprisesApi(api_client)
    body = garm_client.CreateEnterpriseParams() # CreateEnterpriseParams | Parameters used to create the enterprise.

    try:
        # Create enterprise with the given parameters.
        api_response = api_instance.create_enterprise(body)
        print("The response of EnterprisesApi->create_enterprise:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling EnterprisesApi->create_enterprise: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **body** | [**CreateEnterpriseParams**](CreateEnterpriseParams.md)| Parameters used to create the enterprise. | 

### Return type

[**Enterprise**](Enterprise.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | Enterprise |  -  |
**0** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

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
    api_instance = garm_client.EnterprisesApi(api_client)
    enterprise_id = 'enterprise_id_example' # str | Enterprise ID.
    body = garm_client.CreatePoolParams() # CreatePoolParams | Parameters used when creating the enterprise pool.

    try:
        # Create enterprise pool with the parameters given.
        api_response = api_instance.create_enterprise_pool(enterprise_id, body)
        print("The response of EnterprisesApi->create_enterprise_pool:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling EnterprisesApi->create_enterprise_pool: %s\n" % e)
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

# **create_enterprise_scale_set**
> ScaleSet create_enterprise_scale_set(enterprise_id, body)

Create enterprise pool with the parameters given.

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
    api_instance = garm_client.EnterprisesApi(api_client)
    enterprise_id = 'enterprise_id_example' # str | Enterprise ID.
    body = garm_client.CreateScaleSetParams() # CreateScaleSetParams | Parameters used when creating the enterprise scale set.

    try:
        # Create enterprise pool with the parameters given.
        api_response = api_instance.create_enterprise_scale_set(enterprise_id, body)
        print("The response of EnterprisesApi->create_enterprise_scale_set:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling EnterprisesApi->create_enterprise_scale_set: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **enterprise_id** | **str**| Enterprise ID. | 
 **body** | [**CreateScaleSetParams**](CreateScaleSetParams.md)| Parameters used when creating the enterprise scale set. | 

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

# **delete_enterprise**
> APIErrorResponse delete_enterprise(enterprise_id)

Delete enterprise by ID.

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
    api_instance = garm_client.EnterprisesApi(api_client)
    enterprise_id = 'enterprise_id_example' # str | ID of the enterprise to delete.

    try:
        # Delete enterprise by ID.
        api_response = api_instance.delete_enterprise(enterprise_id)
        print("The response of EnterprisesApi->delete_enterprise:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling EnterprisesApi->delete_enterprise: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **enterprise_id** | **str**| ID of the enterprise to delete. | 

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
    api_instance = garm_client.EnterprisesApi(api_client)
    enterprise_id = 'enterprise_id_example' # str | Enterprise ID.
    pool_id = 'pool_id_example' # str | ID of the enterprise pool to delete.

    try:
        # Delete enterprise pool by ID.
        api_response = api_instance.delete_enterprise_pool(enterprise_id, pool_id)
        print("The response of EnterprisesApi->delete_enterprise_pool:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling EnterprisesApi->delete_enterprise_pool: %s\n" % e)
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

# **get_enterprise**
> Enterprise get_enterprise(enterprise_id)

Get enterprise by ID.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.enterprise import Enterprise
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
    api_instance = garm_client.EnterprisesApi(api_client)
    enterprise_id = 'enterprise_id_example' # str | The ID of the enterprise to fetch.

    try:
        # Get enterprise by ID.
        api_response = api_instance.get_enterprise(enterprise_id)
        print("The response of EnterprisesApi->get_enterprise:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling EnterprisesApi->get_enterprise: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **enterprise_id** | **str**| The ID of the enterprise to fetch. | 

### Return type

[**Enterprise**](Enterprise.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | Enterprise |  -  |
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
    api_instance = garm_client.EnterprisesApi(api_client)
    enterprise_id = 'enterprise_id_example' # str | Enterprise ID.
    pool_id = 'pool_id_example' # str | Pool ID.

    try:
        # Get enterprise pool by ID.
        api_response = api_instance.get_enterprise_pool(enterprise_id, pool_id)
        print("The response of EnterprisesApi->get_enterprise_pool:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling EnterprisesApi->get_enterprise_pool: %s\n" % e)
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
    api_instance = garm_client.EnterprisesApi(api_client)
    enterprise_id = 'enterprise_id_example' # str | Enterprise ID.

    try:
        # List enterprise instances.
        api_response = api_instance.list_enterprise_instances(enterprise_id)
        print("The response of EnterprisesApi->list_enterprise_instances:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling EnterprisesApi->list_enterprise_instances: %s\n" % e)
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
    api_instance = garm_client.EnterprisesApi(api_client)
    enterprise_id = 'enterprise_id_example' # str | Enterprise ID.

    try:
        # List enterprise pools.
        api_response = api_instance.list_enterprise_pools(enterprise_id)
        print("The response of EnterprisesApi->list_enterprise_pools:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling EnterprisesApi->list_enterprise_pools: %s\n" % e)
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

# **list_enterprise_scale_sets**
> List[ScaleSet] list_enterprise_scale_sets(enterprise_id)

List enterprise scale sets.

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
    api_instance = garm_client.EnterprisesApi(api_client)
    enterprise_id = 'enterprise_id_example' # str | Enterprise ID.

    try:
        # List enterprise scale sets.
        api_response = api_instance.list_enterprise_scale_sets(enterprise_id)
        print("The response of EnterprisesApi->list_enterprise_scale_sets:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling EnterprisesApi->list_enterprise_scale_sets: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **enterprise_id** | **str**| Enterprise ID. | 

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

# **list_enterprises**
> List[Enterprise] list_enterprises(name=name, endpoint=endpoint)

List all enterprises.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.enterprise import Enterprise
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
    api_instance = garm_client.EnterprisesApi(api_client)
    name = 'name_example' # str | Exact enterprise name to filter by (optional)
    endpoint = 'endpoint_example' # str | Exact endpoint name to filter by (optional)

    try:
        # List all enterprises.
        api_response = api_instance.list_enterprises(name=name, endpoint=endpoint)
        print("The response of EnterprisesApi->list_enterprises:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling EnterprisesApi->list_enterprises: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **name** | **str**| Exact enterprise name to filter by | [optional] 
 **endpoint** | **str**| Exact endpoint name to filter by | [optional] 

### Return type

[**List[Enterprise]**](Enterprise.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | Enterprises |  -  |
**0** | APIErrorResponse |  -  |

[[Back to top]](#) [[Back to API list]](../README.md#documentation-for-api-endpoints) [[Back to Model list]](../README.md#documentation-for-models) [[Back to README]](../README.md)

# **update_enterprise**
> Enterprise update_enterprise(enterprise_id, body)

Update enterprise with the given parameters.

### Example

* Api Key Authentication (Bearer):

```python
import garm_client
from garm_client.models.enterprise import Enterprise
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
    api_instance = garm_client.EnterprisesApi(api_client)
    enterprise_id = 'enterprise_id_example' # str | The ID of the enterprise to update.
    body = garm_client.UpdateEntityParams() # UpdateEntityParams | Parameters used when updating the enterprise.

    try:
        # Update enterprise with the given parameters.
        api_response = api_instance.update_enterprise(enterprise_id, body)
        print("The response of EnterprisesApi->update_enterprise:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling EnterprisesApi->update_enterprise: %s\n" % e)
```



### Parameters


Name | Type | Description  | Notes
------------- | ------------- | ------------- | -------------
 **enterprise_id** | **str**| The ID of the enterprise to update. | 
 **body** | [**UpdateEntityParams**](UpdateEntityParams.md)| Parameters used when updating the enterprise. | 

### Return type

[**Enterprise**](Enterprise.md)

### Authorization

[Bearer](../README.md#Bearer)

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

### HTTP response details

| Status code | Description | Response headers |
|-------------|-------------|------------------|
**200** | Enterprise |  -  |
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
    api_instance = garm_client.EnterprisesApi(api_client)
    enterprise_id = 'enterprise_id_example' # str | Enterprise ID.
    pool_id = 'pool_id_example' # str | ID of the enterprise pool to update.
    body = garm_client.UpdatePoolParams() # UpdatePoolParams | Parameters used when updating the enterprise pool.

    try:
        # Update enterprise pool with the parameters given.
        api_response = api_instance.update_enterprise_pool(enterprise_id, pool_id, body)
        print("The response of EnterprisesApi->update_enterprise_pool:\n")
        pprint(api_response)
    except Exception as e:
        print("Exception when calling EnterprisesApi->update_enterprise_pool: %s\n" % e)
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

