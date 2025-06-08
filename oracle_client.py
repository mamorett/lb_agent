from typing import List, Dict, Any
from datetime import datetime, timedelta
import json
import oci
from oci import config
from oci.logging import LoggingManagementClient
from oci.loggingsearch import LogSearchClient
from oci.loggingsearch.models import SearchLogsDetails

# Simple import
from models import LogEntry

class OracleLogsClient:
    def __init__(self):
        """Initialize Oracle Cloud connection only"""
        try:
            # Initialize Oracle Cloud clients
            self.config = oci.config.from_file(profile_name="SWEDEN")
            self.logging_client = LoggingManagementClient(self.config)
            self.search_client = LogSearchClient(self.config)
            
            # Oracle Cloud identifiers from your log structure
            self.compartment_id = "ocid1.tenancy.oc1..aaaaaaaafpspkvejmkhbeuwq7cdfwvfl2skhgjzrpsegy6ppgf5ijx5skmqq"
            self.log_group_id = "ocid1.loggroup.oc1.eu-stockholm-1.amaaaaaarzyg5cyalxcetb2kpp77z5dungbvwwx6zxrv6oqsfkptb4yrtbna"
            self.log_id = "ocid1.log.oc1.eu-stockholm-1.amaaaaaarzyg5cyamgcm3ulhegg5x6qf7mslsr3z2hhitsm7rf3hdf5vf6iq"
            
            print("✅ Oracle Cloud connection initialized successfully")
            print(f"📋 Targeting log: {self.log_id}")
            
        except Exception as e:
            print(f"❌ Failed to initialize Oracle Cloud connection: {e}")
            raise
    
    def _build_base_query(self) -> str:
        """Build the base query targeting the specific log"""
        # Target the specific log OCID instead of just compartment/log group
        return f'search "{self.compartment_id}/{self.log_group_id}/{self.log_id}"'
    
    def _build_country_query(self, params: Dict[str, Any]) -> str:
        """Build Oracle Cloud Logging query for country search"""
        # Use specific log OCID
        base_query = self._build_base_query()
        
        conditions = []
        
        if params.get('country'):
            conditions.append(f'data.Country = "{params["country"]}"')
        
        if params.get('country_code'):
            conditions.append(f'data.CountryCode = "{params["country_code"]}"')
        
        if conditions:
            base_query += ' | where ' + ' and '.join(conditions)
        
        # Remove limit from query - let pagination handle it
        # if params.get('limit'):
        #     base_query += f' | limit {params["limit"]}'
            
        return base_query
    
    def _build_location_query(self, params: Dict[str, Any]) -> str:
        """Build geographic bounding box query"""
        query = self._build_base_query()
        query += f' | where data.Latitude >= {params["lat_min"]} and data.Latitude <= {params["lat_max"]}'
        query += f' | where data.Longitude >= {params["lon_min"]} and data.Longitude <= {params["lon_max"]}'
        
        # Remove limit from query - let pagination handle it
        # if params.get('limit'):
        #     query += f' | limit {params["limit"]}'
            
        return query
    
    def _build_ip_query(self, params: Dict[str, Any]) -> str:
        """Build IP-based search query"""
        query = self._build_base_query()
        
        if params.get('ip_address'):
            query += f' | where data.IP = "{params["ip_address"]}"'
        elif params.get('ip_range'):
            # For IP range, you might need to implement CIDR matching
            # This is a simplified version
            ip_prefix = params["ip_range"].split('/')[0].rsplit('.', 1)[0]
            query += f' | where data.IP like "{ip_prefix}%"'
        
        # Remove limit from query - let pagination handle it
        # if params.get('limit'):
        #     query += f' | limit {params["limit"]}'
            
        return query
    
    def _build_protocol_query(self, protocol: str, params: Dict[str, Any]) -> str:
        """Build protocol-specific query"""
        query = self._build_base_query()
        query += f' | where data.Protocol = "{protocol}"'
        
        # Remove limit from query - let pagination handle it
        # if params.get('limit'):
        #     query += f' | limit {params["limit"]}'
            
        return query
    
    def _build_isp_query(self, isp: str, params: Dict[str, Any]) -> str:
        """Build ISP-specific query"""
        query = self._build_base_query()
        query += f' | where data.ISP = "{isp}"'
        
        # Remove limit from query - let pagination handle it
        # if params.get('limit'):
        #     query += f' | limit {params["limit"]}'
            
        return query
    
    async def _execute_oracle_query(self, query: str, start_time: datetime, end_time: datetime, max_results: int = None) -> List[Dict]:
        """Execute Oracle query with pagination support - ENHANCED VERSION"""
        all_oracle_logs = []
        page_token = None
        page_count = 0
        
        print(f"🔍 Executing query: {query}")
        print(f"📅 Time range: {start_time} to {end_time}")
        print(f"🎯 Max results: {max_results or 'unlimited'}")
        
        while True:
            try:
                page_count += 1
                print(f"📄 Fetching page {page_count}...")
                
                search_details = SearchLogsDetails(
                    time_start=start_time,
                    time_end=end_time,
                    search_query=query,
                    is_return_field_info=False
                )
                
                # Add pagination token if we have one
                if page_token:
                    search_details.page = page_token
                
                # Execute search
                response = self.search_client.search_logs(search_details)
                
                if not response or not response.data or not response.data.results:
                    print(f"📊 No results on page {page_count}")
                    break
                
                # Parse results using your original working logic
                page_oracle_logs = []
                for result in response.data.results:
                    try:
                        # Parse the JSON log data - YOUR ORIGINAL WORKING CODE
                        log_data = json.loads(result.data) if isinstance(result.data, str) else result.data
                        page_oracle_logs.append(log_data)
                    except json.JSONDecodeError as e:
                        print(f"Failed to parse log JSON: {e}")
                        continue
                
                all_oracle_logs.extend(page_oracle_logs)
                
                print(f"📊 Page {page_count}: +{len(page_oracle_logs)} results (total: {len(all_oracle_logs)})")
                
                # Check if we've hit our limit
                if max_results and len(all_oracle_logs) >= max_results:
                    print(f"🎯 Reached limit of {max_results}")
                    break
                
                # Look for next page token
                page_token = None
                if hasattr(response, 'opc_next_page') and response.opc_next_page:
                    page_token = response.opc_next_page
                elif hasattr(response.data, 'opc_next_page') and response.data.opc_next_page:
                    page_token = response.data.opc_next_page
                elif hasattr(response, 'headers') and response.headers:
                    page_token = response.headers.get('opc-next-page')
                
                if not page_token:
                    print(f"✅ No more pages")
                    break
                
                # Safety limit
                if page_count >= 20:
                    print(f"⚠️ Hit page limit (20)")
                    break
                    
            except Exception as e:
                print(f"❌ Error on page {page_count}: {e}")
                break
        
        # Apply limit and return
        final_results = all_oracle_logs[:max_results] if max_results else all_oracle_logs
        print(f"✅ Found {len(final_results)} log entries")
        return final_results
    
    def _parse_oracle_log_entry(self, oracle_log: Dict) -> LogEntry:
        """Parse Oracle log JSON into LogEntry model - YOUR ORIGINAL WORKING CODE"""
        try:
            log_content = oracle_log.get('logContent', {})
            data = log_content.get('data', {})
            
            # Convert timestamp - Oracle gives milliseconds since epoch
            timestamp_ms = oracle_log.get('datetime', 0)
            timestamp = datetime.fromtimestamp(timestamp_ms / 1000.0)
            
            # Alternative: use the ISO timestamp from logContent.time
            # timestamp = datetime.fromisoformat(log_content.get('time', '').replace('Z', '+00:00'))
            
            return LogEntry(
                timestamp=timestamp,
                ip=data.get('IP', ''),
                protocol=data.get('Protocol', ''),
                latitude=float(data.get('Latitude', 0.0)),
                longitude=float(data.get('Longitude', 0.0)),
                country=data.get('Country', ''),
                country_code=data.get('CountryCode', ''),
                city=data.get('City', ''),
                isp=data.get('ISP', '')
            )
            
        except Exception as e:
            print(f"Error parsing log entry: {e}")
            return None
    
    async def search_logs_by_country(self, params: Dict[str, Any]) -> List[LogEntry]:
        """Search logs by country or country code - WITH PAGINATION"""
        start_time, end_time = self._parse_time_range(params.get('time_range', '24h'))
        query = self._build_country_query(params)
        
        # Pass the limit to the query executor
        max_results = params.get('limit', 1000)
        oracle_logs = await self._execute_oracle_query(query, start_time, end_time, max_results)
        
        log_entries = []
        for oracle_log in oracle_logs:
            entry = self._parse_oracle_log_entry(oracle_log)
            if entry:
                log_entries.append(entry)
        
        return log_entries
    
    async def search_logs_by_location(self, params: Dict[str, Any]) -> List[LogEntry]:
        """Search logs within geographic bounds - WITH PAGINATION"""
        start_time, end_time = self._parse_time_range(params.get('time_range', '24h'))
        query = self._build_location_query(params)
        
        max_results = params.get('limit', 1000)
        oracle_logs = await self._execute_oracle_query(query, start_time, end_time, max_results)
        
        log_entries = []
        for oracle_log in oracle_logs:
            entry = self._parse_oracle_log_entry(oracle_log)
            if entry:
                log_entries.append(entry)
        
        return log_entries
    
    async def search_logs_by_ip(self, params: Dict[str, Any]) -> List[LogEntry]:
        """Search logs by IP address or range - WITH PAGINATION"""
        start_time, end_time = self._parse_time_range(params.get('time_range', '24h'))
        query = self._build_ip_query(params)
        
        max_results = params.get('limit', 1000)
        oracle_logs = await self._execute_oracle_query(query, start_time, end_time, max_results)
        
        log_entries = []
        for oracle_log in oracle_logs:
            entry = self._parse_oracle_log_entry(oracle_log)
            if entry:
                log_entries.append(entry)
        
        return log_entries
    
    async def get_traffic_analytics(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Get aggregated traffic statistics - WITH PAGINATION"""
        start_time, end_time = self._parse_time_range(params.get('time_range', '24h'))
        
        # Get all logs for the time period from the specific log
        base_query = self._build_base_query()
        
        # For analytics, get more data
        analysis_limit = params.get('limit', 5000)
        oracle_logs = await self._execute_oracle_query(base_query, start_time, end_time, analysis_limit)
        
        # Process analytics
        analytics = self._process_analytics(oracle_logs, params.get('group_by', 'country'))
        analytics['time_range'] = params.get('time_range', '24h')
        analytics['total_requests'] = len(oracle_logs)
        analytics['log_source'] = self.log_id
        
        return analytics
    
    def _process_analytics(self, oracle_logs: List[Dict], group_by: str) -> Dict[str, Any]:
        """Process logs into analytics summary - YOUR ORIGINAL WORKING CODE"""
        from collections import Counter
        
        unique_ips = set()
        grouped_data = []
        protocols = []
        countries = []
        cities = []
        isps = []
        
        for oracle_log in oracle_logs:
            try:
                data = oracle_log.get('logContent', {}).get('data', {})
                
                unique_ips.add(data.get('IP', ''))
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
                    
            except Exception as e:
                print(f"Error processing log for analytics: {e}")
                continue
        
        # Generate top lists
        grouped_counter = Counter(grouped_data)
        protocol_counter = Counter(protocols)
        
        return {
            'unique_ips': len(unique_ips),
            'unique_countries': len(set(countries)),
            'unique_cities': len(set(cities)),
            f'top_{group_by}': [
                {'name': item, 'count': count} 
                for item, count in grouped_counter.most_common(10)
            ],
            'protocol_distribution': dict(protocol_counter.most_common()),
            'top_isps': [isp for isp, _ in Counter(isps).most_common(5)]
        }
    
    def _parse_time_range(self, time_range: str) -> tuple[datetime, datetime]:
        """Parse time range string like '24h', '7d', '1w' into datetime objects"""
        now = datetime.utcnow()
        
        if time_range.endswith('h'):
            hours = int(time_range[:-1])
            start_time = now - timedelta(hours=hours)
        elif time_range.endswith('d'):
            days = int(time_range[:-1])
            start_time = now - timedelta(days=days)
        elif time_range.endswith('w'):
            weeks = int(time_range[:-1])
            start_time = now - timedelta(weeks=weeks)
        else:
            # Default to 24 hours
            start_time = now - timedelta(hours=24)
            
        return start_time, now
