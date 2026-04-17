import logging
from datetime import datetime
import importlib
from core.shield import Shield3

# Scrapers to monitor
SCRAPERS = [
    "data.sources.jumbo_scraper",
    "data.sources.lider_scraper",
    "data.sources.santa_isabel_scraper",
    "data.sources.unimarc_scraper"
]

class ScraperGuardian:
    """
    KAIROS Subagent: Monitors the health of all supermarket scrapers.
    Detects if store APIs are down or if our requests are being blocked.
    """
    
    def __init__(self):
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger("ScraperGuardian")
        self.health_results = {}

    def run_health_checks(self):
        """
        Executes check_health() for all registered scrapers.
        """
        self.logger.info(f"--- Starting Scraper Health Audit: {datetime.now().isoformat()} ---")
        
        # We need a session manager or just clean requests
        from curl_cffi import requests as cffi_requests
        session = cffi_requests.Session(impersonate="chrome")
        
        import importlib
        
        for module_path in SCRAPERS:
            try:
                module = importlib.import_module(module_path)
                if hasattr(module, 'check_health'):
                    success, msg = module.check_health(session=session)
                    
                    # Shield 3.0: Threat Analysis
                    proxy_headers = getattr(session, 'headers', {})
                    is_threat, threat_msg, score = Shield3.analyze_waf_threat(proxy_headers)
                    host_status = "🛡️ SECURE" if not is_threat else f"⚠️ THREAT ({score}%)"
                    
                    status = "✅ OK" if success else "❌ FAIL"
                    self.logger.info(f"[{module_path}] {status} | Env: {host_status}: {msg}")
                    if is_threat:
                        self.logger.warning(f"  [SHIELD ALERT] {threat_msg}")
                    
                    self.health_results[module_path] = (success, msg, score)
                else:
                    self.logger.warning(f"[{module_path}] Scraper missing check_health() function.")
            except Exception as e:
                self.logger.error(f"[{module_path}] Audit error: {e}")
                self.health_results[module_path] = (False, str(e))

        return self.health_results

    def get_summary(self):
        """
        Returns a human-readable summary of the last audit.
        """
        lines = [f"### Scraper Health Summary ({datetime.now().strftime('%Y-%m-%d %H:%M')})"]
        for path, (success, msg, score) in self.health_results.items():
            icon = "✅" if success else "❌"
            shield_icon = "🛡️" if score < 50 else "⚠️"
            store = path.split('.')[-1].replace('_scraper', '').capitalize()
            lines.append(f"- **{store}**: {icon} {msg} | Security: {shield_icon} ({score}%)")
        return "\n".join(lines)

if __name__ == "__main__":
    guardian = ScraperGuardian()
    guardian.run_health_checks()
    print("\n" + guardian.get_summary())
