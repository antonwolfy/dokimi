"""Analyze project to gather signals for persona generation."""

import logging
from typing import Dict, List, Any, Optional
from pathlib import Path
import json

try:
    from github import Github, GithubException
    GITHUB_AVAILABLE = True
except ImportError:
    GITHUB_AVAILABLE = False

logger = logging.getLogger(__name__)


class PersonaAnalyzer:
    """
    Analyze a GitHub project to extract signals for persona discovery.
    
    Gathers information from:
    - README (use cases, getting started)
    - Documentation structure
    - GitHub issues (questions, problems)
    - Code examples
    """
    
    def __init__(self, github_token: Optional[str] = None):
        """
        Initialize analyzer.
        
        Args:
            github_token: GitHub personal access token (optional, for higher rate limits)
        """
        self.github_token = github_token
        self._github_client = None
        
        if not GITHUB_AVAILABLE:
            logger.warning("PyGithub not available. GitHub analysis will be limited.")
    
    @property
    def github_client(self):
        """Lazy-load GitHub client."""
        if self._github_client is None and GITHUB_AVAILABLE:
            if self.github_token:
                self._github_client = Github(self.github_token)
            else:
                self._github_client = Github()  # Anonymous (lower rate limit)
        return self._github_client
    
    def analyze_repository(self, repo_name: str) -> Dict[str, Any]:
        """
        Analyze a GitHub repository for persona signals.
        
        Args:
            repo_name: Repository in format "owner/repo"
            
        Returns:
            Dictionary with analysis results:
            {
                "readme_content": str,
                "use_cases": List[str],
                "issues_analysis": {
                    "common_questions": List[str],
                    "common_labels": List[str],
                    "sample_issues": List[dict]
                },
                "api_patterns": List[str]
            }
        """
        if not self.github_client:
            logger.error("GitHub client not available")
            return self._empty_analysis()
        
        try:
            logger.info(f"Analyzing repository: {repo_name}")
            repo = self.github_client.get_repo(repo_name)
            
            analysis = {
                "readme_content": self._get_readme(repo),
                "use_cases": self._extract_use_cases(repo),
                "issues_analysis": self._analyze_issues(repo),
                "api_patterns": self._extract_api_patterns(repo),
                "description": repo.description or "",
                "topics": repo.get_topics()
            }
            
            logger.info(f"Analysis complete: {len(analysis['use_cases'])} use cases, "
                       f"{len(analysis['issues_analysis']['sample_issues'])} sample issues")
            
            return analysis
            
        except GithubException as e:
            logger.error(f"GitHub API error: {e}")
            return self._empty_analysis()
        except Exception as e:
            logger.error(f"Analysis error: {e}")
            return self._empty_analysis()
    
    def _get_readme(self, repo) -> str:
        """Extract README content."""
        try:
            readme = repo.get_readme()
            return readme.decoded_content.decode('utf-8')
        except:
            return ""
    
    def _extract_use_cases(self, repo) -> List[str]:
        """
        Extract use cases from README and docs.
        
        Looks for sections like:
        - Use Cases
        - When to Use
        - Applications
        - Examples
        """
        use_cases = []
        readme = self._get_readme(repo)
        
        if not readme:
            return use_cases
        
        # Simple heuristic: look for list items after "use case" headers
        lines = readme.lower().split('\n')
        in_use_case_section = False
        
        for i, line in enumerate(lines):
            if any(keyword in line for keyword in ['use case', 'application', 'when to use']):
                in_use_case_section = True
                continue
            
            if in_use_case_section:
                if line.startswith('#'):  # New section
                    in_use_case_section = False
                elif line.strip().startswith(('-', '*', '•')):
                    use_cases.append(line.strip().lstrip('-*• '))
        
        return use_cases[:10]  # Limit to top 10
    
    def _analyze_issues(self, repo, limit: int = 50) -> Dict[str, Any]:
        """
        Analyze recent issues for common question patterns.
        
        Focuses on:
        - Questions (label:question)
        - Help requests (label:help wanted, label:support)
        - Bug reports that reveal use cases
        """
        try:
            # Fetch issues with question-related labels
            question_labels = ['question', 'help wanted', 'support', 'documentation']
            issues_to_analyze = []
            
            for label in question_labels:
                try:
                    issues = repo.get_issues(state='all', labels=[label])
                    issues_to_analyze.extend(list(issues[:limit // len(question_labels)]))
                except:
                    continue
            
            # Extract patterns
            common_questions = []
            sample_issues = []
            
            for issue in issues_to_analyze[:limit]:
                title = issue.title
                common_questions.append(title)
                
                sample_issues.append({
                    "title": title,
                    "labels": [label.name for label in issue.labels],
                    "url": issue.html_url
                })
            
            # Get common labels
            label_counts = {}
            for issue in issues_to_analyze:
                for label in issue.labels:
                    label_counts[label.name] = label_counts.get(label.name, 0) + 1
            
            common_labels = sorted(label_counts.items(), key=lambda x: x[1], reverse=True)[:10]
            
            return {
                "common_questions": common_questions[:20],
                "common_labels": [label for label, _ in common_labels],
                "sample_issues": sample_issues[:10]
            }
            
        except Exception as e:
            logger.error(f"Issue analysis error: {e}")
            return {"common_questions": [], "common_labels": [], "sample_issues": []}
    
    def _extract_api_patterns(self, repo) -> List[str]:
        """
        Extract common API patterns from code examples.
        
        Looks for:
        - Frequently used class/function names
        - Import patterns
        - Code snippets in docs
        """
        # Simplified version: extract from README code blocks
        readme = self._get_readme(repo)
        if not readme:
            return []
        
        patterns = []
        in_code_block = False
        
        for line in readme.split('\n'):
            if line.strip().startswith('```'):
                in_code_block = not in_code_block
                continue
            
            if in_code_block:
                # Extract likely API calls (simplified heuristic)
                if '::' in line or '.' in line:
                    patterns.append(line.strip())
        
        return patterns[:20]
    
    def _empty_analysis(self) -> Dict[str, Any]:
        """Return empty analysis structure."""
        return {
            "readme_content": "",
            "use_cases": [],
            "issues_analysis": {
                "common_questions": [],
                "common_labels": [],
                "sample_issues": []
            },
            "api_patterns": [],
            "description": "",
            "topics": []
        }
    
    def save_analysis(self, analysis: Dict[str, Any], output_path: Path):
        """Save analysis to JSON file."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w') as f:
            json.dump(analysis, f, indent=2)
        logger.info(f"Saved analysis to {output_path}")
