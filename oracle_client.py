from typing import List, Dict, Any
from datetime import datetime, timedelta
import json
import oci
from oci import config
from oci.logging import LoggingManagementClient
from oci.loggingsearch import LogSearchClient
from oci.loggingsearch.models import SearchLogsDetails

from models import LogEntry

class OracleLogsClient:
    def __init__(self, profile_name="SWEDEN"):
        """Initialize Oracle Cloud connection"""
        try:
            # Initialize Oracle Cloud clients with specified profile
            self.config = oci.config.from_file(profile_name=profile_name)
            self.logging_client = LoggingManagementClient(self.config)
            self.search_client = LogSearchClient(self.config)
            
            # Oracle Cloud identifiers from your log structure
            self.compartment_id = "ocid1.tenancy.oc1..aaaaaaaafpspkvejmkhbeuwq7cdfwvfl2skhgjzrpsegy6ppgf5ijx5skmqq"
            self.log_group_id = "ocid1.loggroup.oc1.eu-stockholm-1.amaaaaaarzyg5cyalxcetb2kpp77z5dungbvwwx6zxrv6oqsfkptb4yrtbna"
            self.log_id = "ocid1.log.oc1.eu-stockholm-1.amaaaaaarzyg5cyamgcm3ulhegg5x6qf7mslsr3z2hhitsm7rf3hdf5vf6iq"
            
            print("✅ Oracle Cloud connection initialized successfully")
            print(f"🇸🇪 Using profile: {profile_name}")
            print(f"📋 Targeting log: {self.log_id}")
            
        except Exception as e:
            print(f"❌ Failed to initialize Oracle Cloud connection with profile '{profile_name}': {e}")
            raise
    
    def _build_base_query(self) -> str:
        """Build the base query targeting the specific log"""
        # Target the specific log OCID instead of just compartment/log group
        return f'search "{self.compartment_id}/{self.log_group_id}/{self.log_id}"'
    
    def _build_country_query(self, params: Dict[str, Any]) -> str:
        """Build query for country search"""
        query = self._build_base_query()
        
        # Add country filter
        if params.get('country'):
            country = params['country'].replace('"', '\\"')
            query += f' | where data.Country = "{country}"'
        elif params.get('country_code'):
            code = params['country_code'].replace('"', '\\"')
            query += f' | where data.CountryCode = "{code}"'
        
        print(f"🔍 Built country query: {query}")
        return query
    
    def _build_ip_query(self, params: Dict[str, Any]) -> str:
        """Build query for IP search"""
        query = self._build_base_query()
        
        if params.get('ip_address'):
            ip = params['ip_address'].replace('"', '\\"')
            query += f' | where data.IP = "{ip}"'
        elif params.get('ip_range'):
            # For IP ranges, use contains or startswith
            ip_prefix = params['ip_range'].split('/')[0]
            query += f' | where data.IP contains "{ip_prefix}"'
        
        print(f"🔍 Built IP query: {query}")
        return query
    
    def _build_location_query(self, params: Dict[str, Any]) -> str:
        """Build query for location search"""
        query = self._build_base_query()
        
        # Add geographic bounds
        query += f' | where data.Latitude >= {params["lat_min"]}'
        query += f' | where data.Latitude <= {params["lat_max"]}'
        query += f' | where data.Longitude >= {params["lon_min"]}'
        query += f' | where data.Longitude <= {params["lon_max"]}'
        
        print(f"🔍 Built location query: {query}")
        return query
    
    def _build_analytics_query(self, params: Dict[str, Any]) -> str:
        """Build query for analytics"""
        query = self._build_base_query()
        
        # For analytics, we usually want all data without specific filters
        # unless country is specified
        if params.get('country'):
            country = params['country'].replace('"', '\\"')
            query += f' | where data.Country = "{country}"'
        
        print(f"🔍 Built analytics query: {query}")
        return query
    
    def _parse_time_range(self, time_range: str) -> tuple[datetime, datetime]:
        """Parse time range string into start and end datetime objects"""
        end_time = datetime.utcnow()
        
        if time_range.endswith('h'):
            hours = int(time_range[:-1])
            start_time = end_time - timedelta(hours=hours)
        elif time_range.endswith('d'):
            days = int(time_range[:-1])
            start_time = end_time - timedelta(days=days)
        elif time_range.endswith('w'):
            weeks = int(time_range[:-1])
            start_time = end_time - timedelta(weeks=weeks)
        else:
            # Default to 24 hours
            start_time = end_time - timedelta(hours=24)
        
        return start_time, end_time
    
    def _validate_query(self, query: str) -> bool:
        """Validate Oracle Cloud Logging query syntax"""
        if not query.strip():
            return False
        
        if not query.strip().startswith('search '):
            return False
        
        if self.log_id not in query:
            return False
        
        return True
    
    def _get_next_page_token(self, response) -> str:
        """Extract next page token from Oracle response"""
        try:
            # Try different possible locations for pagination token
            if hasattr(response, 'opc_next_page') and response.opc_next_page:
                return response.opc_next_page
                
            if hasattr(response.data, 'opc_next_page') and response.data.opc_next_page:
                return response.data.opc_next_page
                
            if hasattr(response, 'headers') and response.headers:
                headers = response.headers
                return (headers.get('opc-next-page') or 
                       headers.get('x-next-page') or 
                       headers.get('next-page'))
            
            return None
            
        except Exception as e:
            print(f"⚠️ Error extracting page token: {e}")
            return None
    
    async def _execute_oracle_query(self, query: str, start_time: datetime, end_time: datetime, max_results: int = None) -> List[Dict]:
        """Execute Oracle Cloud Logging query with pagination - return same format as original"""
        
        if not self._validate_query(query):
            print(f"❌ Invalid query format: {query}")
            return []
        
        all_results = []
        page_token = None
        page_count = 0
        
        print(f"🔍 Executing query: {query}")
        print(f"🎯 Max results: {max_results or 'unlimited'}")
        
        while True:
            try:
                page_count += 1
                print(f"📄 Fetching page {page_count}...")
                
                search_request = SearchLogsDetails(
                    time_start=start_time,
                    time_end=end_time,
                    search_query=query,
                    is_return_field_info=False
                )
                
                if page_token:
                    search_request.page = page_token
                
                response = self.search_client.search_logs(search_request)
                
                if not response or not response.data or not response.data.results:
                    print(f"📊 No results on page {page_count}")
                    break
                
                # Convert SearchResult objects to the format the original code expected
                batch_results = []
                for result in response.data.results:
                    # Convert SearchResult to dict format that original code expected
                    try:
                        if hasattr(result, '__dict__'):
                            batch_results.append(result.__dict__)
                        else:
                            batch_results.append(result)
                    except:
                        batch_results.append(result)
                
                all_results.extend(batch_results)
                
                print(f"📊 Page {page_count}: +{len(batch_results)} results (total: {len(all_results)})")
                
                if max_results and len(all_results) >= max_results:
                    break
                
                page_token = self._get_next_page_token(response)
                if not page_token:
                    break
                    
                if page_count >= 50:
                    break
                    
            except Exception as e:
                print(f"❌ Error on page {page_count}: {e}")
                break
        
        final_results = all_results[:max_results] if max_results else all_results
        print(f"🎉 Returning {len(final_results)} results")
        
        return final_results

    
    def _convert_oracle_log_to_entry(self, oracle_log) -> LogEntry:
        """Convert Oracle Cloud log entry to our LogEntry model - handle both formats"""
        try:
            # Handle different response formats
            log_content = None
            timestamp_str = None
            
            # Case 1: Original format (dict-like)
            if hasattr(oracle_log, 'get') or isinstance(oracle_log, dict):
                log_content = oracle_log.get('logContent', {})
                data = log_content.get('data', {})
                timestamp_str = oracle_log.get('time', '')
                
            # Case 2: SearchResult object format  
            elif hasattr(oracle_log, 'data'):
                # This might be the new pagination format
                if hasattr(oracle_log.data, 'get'):
                    data = oracle_log.data
                else:
                    # Convert object to dict
                    data = oracle_log.data.__dict__ if hasattr(oracle_log.data, '__dict__') else {}
                
                timestamp_str = getattr(oracle_log, 'time', '') or getattr(oracle_log, 'timestamp', '')
                
            # Case 3: Direct data object
            else:
                data = oracle_log.__dict__ if hasattr(oracle_log, '__dict__') else {}
                timestamp_str = ''
            
            # Parse timestamp
            timestamp = datetime.utcnow()
            if timestamp_str:
                try:
                    if timestamp_str.endswith('Z'):
                        timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                    else:
                        timestamp = datetime.fromisoformat(timestamp_str)
                except:
                    pass
            
            # Safe data extraction
            def safe_get(data_obj, key, default=''):
                if hasattr(data_obj, 'get'):
                    return data_obj.get(key, default)
                elif hasattr(data_obj, key):
                    return getattr(data_obj, key, default)
                else:
                    return default
            
            return LogEntry(
                timestamp=timestamp,
                ip=safe_get(data, 'IP'),
                country=safe_get(data, 'Country'),
                country_code=safe_get(data, 'CountryCode'),
                city=safe_get(data, 'City'),
                latitude=float(safe_get(data, 'Latitude', 0)) if safe_get(data, 'Latitude') else None,
                longitude=float(safe_get(data, 'Longitude', 0)) if safe_get(data, 'Longitude') else None,
                isp=safe_get(data, 'ISP'),
                protocol=safe_get(data, 'Protocol'),
                raw_data=oracle_log
            )
            
        except Exception as e:
            print(f"❌ Error converting Oracle log: {e}")
            print(f"   Log type: {type(oracle_log)}")
            return None


    
    async def search_logs_by_country(self, params: Dict[str, Any]) -> List[LogEntry]:
        """Search logs by country with pagination"""
        start_time, end_time = self._parse_time_range(params.get('time_range', '24h'))
        query = self._build_country_query(params)
        
        max_results = params.get('limit', 1000)
        
        oracle_logs = await self._execute_oracle_query(query, start_time, end_time, max_results)
        
        # Convert to LogEntry objects
        log_entries = []
        for oracle_log in oracle_logs:
            try:
                log_entry = self._convert_oracle_log_to_entry(oracle_log)
                if log_entry:
                    log_entries.append(log_entry)
            except Exception as e:
                print(f"Error converting log entry: {e}")
                continue
        
        return log_entries
    
    async def search_logs_by_ip(self, params: Dict[str, Any]) -> List[LogEntry]:
        """Search logs by IP with pagination"""
        start_time, end_time = self._parse_time_range(params.get('time_range', '24h'))
        query = self._build_ip_query(params)
        
        max_results = params.get('limit', 1000)
        
        oracle_logs = await self._execute_oracle_query(query, start_time, end_time, max_results)
        
        log_entries = []
        for oracle_log in oracle_logs:
            try:
                log_entry = self._convert_oracle_log_to_entry(oracle_log)
                if log_entry:
                    log_entries.append(log_entry)
            except Exception as e:
                print(f"Error converting log entry: {e}")
                continue
        
        return log_entries
    
    async def search_logs_by_location(self, params: Dict[str, Any]) -> List[LogEntry]:
        """Search logs by location with pagination"""
        start_time, end_time = self._parse_time_range(params.get('time_range', '24h'))
        query = self._build_location_query(params)
        
        max_results = params.get('limit', 1000)
        
        oracle_logs = await self._execute_oracle_query(query, start_time, end_time, max_results)
        
        log_entries = []
        for oracle_log in oracle_logs:
            try:
                log_entry = self._convert_oracle_log_to_entry(oracle_log)
                if log_entry:
                    log_entries.append(log_entry)
            except Exception as e:
                print(f"Error converting log entry: {e}")
                continue
        
        return log_entries
    
    def _process_analytics(self, oracle_logs: List[Dict], group_by: str) -> Dict[str, Any]:
        """Process logs into analytics summary"""
        from collections import Counter
        
        unique_ips = set()
        grouped_data = []
        protocols = []
        countries = []
        cities = []
        isps = []
        
        for oracle_log in oracle_logs:
            try:
                log_content = oracle_log.get('logContent', {})
                data = log_content.get('data', {})
                
                ip = data.get('IP', '')
                unique_ips.add(ip)
                protocols.append(data.get('Protocol', ''))
                countries.append(data.get('Country', ''))
                cities.append(data.get('City', ''))
                isps.append(data.get('ISP', ''))
                
                # Group by requested field
                if group_by == 'country':
                    grouped_data.append(data.get('Country', 'Unknown'))
                elif group_by == 'city':
                    grouped_data.append(f"{data.get('City', 'Unknown')}, {data.get('Country', '')}")
                elif group_by == 'isp':
                    grouped_data.append(data.get('ISP', 'Unknown'))
                elif group_by == 'protocol':
                    grouped_data.append(data.get('Protocol', 'Unknown'))
                elif group_by == 'ip':
                    grouped_data.append(ip)
                    
            except Exception as e:
                print(f"Error processing log for analytics: {e}")
                continue
        
        # Generate top lists
        grouped_counter = Counter(grouped_data)
        protocol_counter = Counter(protocols)
        
        result = {
            'total_requests': len(oracle_logs),
            'unique_ips': len(unique_ips),
            'unique_countries': len(set(countries)),
            'unique_cities': len(set(cities)),
            f'top_{group_by}': [
                {'name': item, 'count': count} 
                for item, count in grouped_counter.most_common(20)
            ],
            'protocol_distribution': dict(protocol_counter.most_common()),
            'top_isps': [isp for isp, _ in Counter(isps).most_common(10)]
        }
        
        # If grouping by IP, add detailed IP list
        if group_by == 'ip':
            result['unique_ip_details'] = [
                {'ip': ip, 'requests': count}
                for ip, count in grouped_counter.most_common(1000)
            ]
        
        return result
    
    async def get_traffic_analytics(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Get traffic analytics with pagination"""
        start_time, end_time = self._parse_time_range(params.get('time_range', '24h'))
        query = self._build_analytics_query(params)
        
        # For analytics, we might want more data to analyze
        analysis_limit = params.get('limit', 5000)
        
        oracle_logs = await self._execute_oracle_query(query, start_time, end_time, analysis_limit)
        
        # Process analytics
        group_by = params.get('group_by', 'country')
        analytics = self._process_analytics(oracle_logs, group_by)
        
        # Add metadata
        analytics['query_info'] = {
            'time_range': params.get('time_range', '24h'),
            'total_logs_analyzed': len(oracle_logs),
            'requested_limit': analysis_limit,
            'group_by': group_by,
            'country_filter': params.get('country', 'All countries')
        }
        
        return analytics
    
    async def test_basic_query(self):
        """Test basic query syntax"""
        simple_query = self._build_base_query()
        
        start_time = datetime.utcnow() - timedelta(hours=1)
        end_time = datetime.utcnow()
        
        print(f"🧪 Testing basic query: {simple_query}")
        
        try:
            search_request = SearchLogsDetails(
                time_start=start_time,
                time_end=end_time,
                search_query=simple_query,
                is_return_field_info=False
            )
            
            response = self.search_client.search_logs(search_request)
            
            if response and response.data and response.data.results:
                print(f"✅ Basic query works! Got {len(response.data.results)} results")
                
                # Show first result structure
                if response.data.results:
                    first_result = response.data.results[0]
                    print(f"📋 First result keys: {list(first_result.keys()) if isinstance(first_result, dict) else 'Not a dict'}")
                    
            else:
                print(f"❌ Basic query returned no results")
                
        except Exception as e:
            print(f"❌ Basic query failed: {e}")
