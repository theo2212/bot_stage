from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.live import Live
from rich.text import Text
from rich.control import Control
from datetime import datetime

class Dashboard:
    def __init__(self):
        self.console = Console()
        self.logs = []
        self.jobs = []
        self.status = "Initializing..."
        self.last_check = "Never"
        self.stats = {
            "jobs_scanned": 0,
            "ai_matches": 0,
            "start_time": datetime.now()
        }
    
    def dump_state(self):
        import json, os
        os.makedirs("data", exist_ok=True)
        state = {
            "status": self.status,
            "logs": self.logs,
            "jobs": self.jobs,
            "stats": {
                "jobs_scanned": self.stats["jobs_scanned"],
                "ai_matches": self.stats["ai_matches"]
            }
        }
        try:
            with open("data/live_state.json", "w", encoding="utf-8") as f:
                json.dump(state, f)
        except: pass

    def update_stats(self, scanned=0, matches=0):
        self.stats["jobs_scanned"] += scanned
        self.stats["ai_matches"] += matches
        
        if hasattr(self, 'live_context') and self.live_context:
            self.live_context.update(self.generate_layout())
        self.dump_state()
    
    def log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}"
        self.logs.append(log_entry)
        if len(self.logs) > 15:
            self.logs.pop(0)
        
        # In CI/GitHub Actions, we need to actually print to see the logs
        if os.environ.get("GITHUB_ACTIONS") == "true":
            print(f"DEBUG: {log_entry}")
        
        # Force redraw if we have a live context linked!
        if hasattr(self, 'live_context') and self.live_context:
            self.live_context.update(self.generate_layout())
        self.dump_state()

    def add_job_row(self, source, company, title, status):
        self.jobs.append({"source": source, "company": company, "title": title, "status": status})
        if len(self.jobs) > 10:
            self.jobs.pop(0)
        self.dump_state()

    def set_status(self, status):
        self.status = status
        if "Checking" in status:
            self.last_check = datetime.now().strftime("%H:%M:%S")
            
        if hasattr(self, 'live_context') and self.live_context:
            self.live_context.update(self.generate_layout())
        self.dump_state()

    def generate_layout(self):
        layout = Layout()
        layout.split(
            Layout(name="header", size=3),
            Layout(name="main", ratio=1),
            Layout(name="footer", size=3)
        )
        layout["main"].split_row(
            Layout(name="left", ratio=1),
            Layout(name="right", ratio=2)
        )
        layout["left"].split_column(
            Layout(name="stats", size=9),
            Layout(name="logs")
        )

        # Header
        layout["header"].update(
            Panel(Text("Stage Hunter 3000 • Active Monitoring", justify="center", style="bold green"), style="green")
        )

        # Left / Top: Live Statistics
        elapsed = datetime.now() - self.stats["start_time"]
        elapsed_str = str(elapsed).split('.')[0]
        
        stats_text = (
            f"[bold cyan]Session Time:[/] {elapsed_str}\n"
            f"[bold cyan]Jobs Scanned:[/] {self.stats['jobs_scanned']}\n"
            f"[bold cyan]High AI Matches:[/] {self.stats['ai_matches']}\n\n"
            f"[bold cyan]Current Status:[/] {self.status}\n"
            f"[bold cyan]Last Check:[/] {self.last_check}"
        )
        layout["stats"].update(Panel(stats_text, title="Live Statistics", border_style="cyan"))

        # Left / Bottom: Activity Log
        log_text = "\n".join(self.logs[-15:]) # Keep last 15
        layout["logs"].update(
            Panel(log_text, title="Activity Log", border_style="blue")
        )

        # Right: Jobs Table
        table = Table(expand=True)
        table.add_column("Source", style="cyan")
        table.add_column("Company", style="magenta")
        table.add_column("Role", style="green")
        table.add_column("Status", style="yellow")
        
        for job in reversed(self.jobs):
            table.add_row(job['source'], job['company'], job['title'], job['status'])

        layout["right"].update(
            Panel(table, title="Detected Opportunities", border_style="yellow")
        )

        # Footer
        layout["footer"].update(
             Panel(Text("Press Ctrl+C to stop • Running locally", justify="center", style="italic grey50"))
        )
        
        return layout
