import asyncio
import json
import re
from oracle_client import OracleLogsClient
import ollama

class OllamaOracleLogsAgent:
    def __init__(self, model_name="mistral-nemo:12b"):
        self.oracle_client = OracleLogsClient()
        self.model_name = model_name
        
    async def chat_with_logs(self, user_message: str) -> str:
        """Process user message and interact with Oracle logs"""
        
        # Analyze user intent
        intent = self._analyze_intent(user_message)
        
        # Execute appropriate log query
        log_data = await self._execute_log_query(intent, user_message)
        
        # Generate response with Ollama
        response = self._generate_response(user_message, log_data)
        
        return response
    
    def _analyze_intent(self, message: str) -> dict:
        """Enhanced intent analysis with better time range extraction"""
        message_lower = message.lower()
        
        intent = {
            "action": "analytics",
            "params": {"time_range": "24h", "limit": 1000}
        }
        
        # Extract time ranges with regex
        time_range = self._extract_time_range(message_lower)
        if time_range:
            intent["params"]["time_range"] = time_range
        
        # Detect unique IP requests
        if any(phrase in message_lower for phrase in [
            "unique ip", "unique ips", "distinct ip", "different ip", 
            "how many ip", "ip addresses", "unique visitors", "distinct visitors"
        ]):
            intent["action"] = "analytics"
            intent["params"]["group_by"] = "ip"
        
        # Country search
        elif any(word in message_lower for word in ["country", "from"]):
            intent["action"] = "search_country"
            # Extract country if mentioned
            countries = ["united states", "usa", "germany", "france", "china", "russia", "sweden", "norway"]
            for country in countries:
                if country in message_lower:
                    intent["params"]["country"] = country.title()
        
        # IP search
        elif any(word in message_lower for word in ["ip", "address"]) and "unique" not in message_lower:
            intent["action"] = "search_ip"
            # Extract IP if present
            ip_match = re.search(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', message)
            if ip_match:
                intent["params"]["ip_address"] = ip_match.group()
        
        # Geographic search
        elif any(word in message_lower for word in ["location", "geographic", "lat", "lon"]):
            intent["action"] = "search_location"
        
        # Extract limit/count requests
        limit = self._extract_limit(message_lower)
        if limit:
            intent["params"]["limit"] = limit
        
        return intent
    
    def _extract_time_range(self, message: str) -> str:
        """Extract time range from natural language"""
        
        # Pattern matching for various time expressions
        patterns = [
            # "150 hours", "last 150 hours", "past 150 hours"
            (r'(?:last|past|previous)?\s*(\d+)\s*hours?', lambda m: f"{m.group(1)}h"),
            
            # "6 days", "last 6 days", "past 6 days"  
            (r'(?:last|past|previous)?\s*(\d+)\s*days?', lambda m: f"{m.group(1)}d"),
            
            # "2 weeks", "last 2 weeks"
            (r'(?:last|past|previous)?\s*(\d+)\s*weeks?', lambda m: f"{int(m.group(1)) * 7}d"),
            
            # "1 month", "last month" (approximate as 30 days)
            (r'(?:last|past|previous)?\s*(\d+)\s*months?', lambda m: f"{int(m.group(1)) * 30}d"),
            
            # Specific phrases
            (r'yesterday', lambda m: "24h"),
            (r'last week', lambda m: "7d"),
            (r'past week', lambda m: "7d"),
            (r'this week', lambda m: "7d"),
            (r'last month', lambda m: "30d"),
            (r'past month', lambda m: "30d"),
        ]
        
        for pattern, converter in patterns:
            match = re.search(pattern, message)
            if match:
                return converter(match)
        
        return None
    
    def _extract_limit(self, message: str) -> int:
        """Extract limit/count from natural language"""
        
        patterns = [
            # "top 20", "first 50", "show 100"
            r'(?:top|first|show|limit)\s+(\d+)',
            # "20 unique", "50 different"  
            r'(\d+)\s+(?:unique|different|distinct)',
            # "maximum 100", "max 200"
            r'(?:maximum|max)\s+(\d+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, message)
            if match:
                return int(match.group(1))
        
        return None
    
    async def _execute_log_query(self, intent: dict, original_message: str) -> dict:
        """Execute the appropriate Oracle log query"""
        try:
            action = intent["action"]
            params = intent["params"]
            
            print(f"🔍 Executing {action} with params: {params}")
            
            if action == "search_country":
                logs = await self.oracle_client.search_logs_by_country(params)
                return {"type": "logs", "data": logs, "count": len(logs)}
            
            elif action == "search_ip":
                logs = await self.oracle_client.search_logs_by_ip(params)
                return {"type": "logs", "data": logs, "count": len(logs)}
            
            elif action == "search_location":
                # Default to some geographic bounds if not specified
                if "lat_min" not in params:
                    params.update({
                        "lat_min": 40.0, "lat_max": 45.0,
                        "lon_min": -80.0, "lon_max": -70.0
                    })
                logs = await self.oracle_client.search_logs_by_location(params)
                return {"type": "logs", "data": logs, "count": len(logs)}
            
            else:  # analytics
                analytics = await self.oracle_client.get_traffic_analytics(params)
                return {"type": "analytics", "data": analytics}
                
        except Exception as e:
            return {"type": "error", "message": str(e)}
    
    def _generate_response(self, user_message: str, log_data: dict) -> str:
        """Generate response using Ollama"""
        
        # Prepare context for Ollama
        if log_data["type"] == "logs":
            context = f"""
User asked: {user_message}

I found {log_data['count']} log entries from Oracle Cloud:

Recent entries:
"""
            for i, log in enumerate(log_data["data"][:5]):
                context += f"- {log.timestamp}: {log.ip} from {log.city}, {log.country} ({log.isp}) via {log.protocol}\n"
            
            if log_data['count'] > 5:
                context += f"... and {log_data['count'] - 5} more entries\n"
        
        elif log_data["type"] == "analytics":
            analytics = log_data["data"]
            context = f"""
User asked: {user_message}

Oracle Cloud Traffic Analytics:
- Total requests: {analytics.get('total_requests', 0)}
- Unique IPs: {analytics.get('unique_ips', 0)}
- Unique countries: {analytics.get('unique_countries', 0)}
- Time range: {analytics.get('time_range', 'N/A')}
"""
            
            # Handle IP-specific analytics
            if analytics.get('top_ip'):
                context += f"\nTop IP addresses:\n"
                for ip_data in analytics['top_ip'][:10]:
                    context += f"- {ip_data['name']}: {ip_data['count']} requests\n"
            
            if analytics.get('top_country'):
                context += f"\nTop countries: {analytics.get('top_country', [])}\n"
            
            context += f"Protocol distribution: {analytics.get('protocol_distribution', {})}\n"
        
        else:  # error
            context = f"Error retrieving log data: {log_data['message']}"
        
        # Generate response with Ollama
        prompt = f"""
Based on the Oracle Cloud log data below, provide a helpful analysis and answer to the user's question.
Focus on answering their specific question about time ranges, unique IPs, or other metrics they asked about.

{context}

Please provide insights, patterns, or specific answers based on this data.
"""
        
        try:
            response = ollama.chat(
                model=self.model_name,
                messages=[
                    {
                        'role': 'user',
                        'content': prompt
                    }
                ]
            )
            return response['message']['content']
        except Exception as e:
            return f"Generated summary based on log data, but Ollama error: {e}\n\n{context}"

# Usage example
async def main():
    agent = OllamaOracleLogsAgent("mistral-nemo:12b")
    
    print("🤖 Oracle Logs Agent with Ollama")
    print("Examples:")
    print("- 'Show me unique IPs from the last 150 hours'")
    print("- 'What are the top 20 IP addresses from the past 6 days?'")
    print("- 'Get traffic from Sweden in the last week'")
    print("- 'Show me 50 unique visitors from yesterday'")
    print()
    
    while True:
        user_input = input("\n🤖 Ask about your Oracle logs: ")
        if user_input.lower() in ['quit', 'exit']:
            break
            
        print("🔍 Analyzing logs...")
        response = await agent.chat_with_logs(user_input)
        print(f"\n📊 Analysis:\n{response}")

if __name__ == "__main__":
    asyncio.run(main())
