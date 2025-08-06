from typing import List, Dict, Optional, Literal
from pydantic import BaseModel, Field

class QueryAnalysis(BaseModel):
    """Enhanced query analysis with ticker and temporal extraction"""
    tickers: List[str] = Field(default_factory=list, description="Extracted stock tickers")
    time_periods: List[str] = Field(default_factory=list, description="Extracted time references")
    document_types: List[str] = Field(default_factory=list, description="Required SEC filing types")
    query_type: Literal[
        "single_ticker", "multi_ticker_comparison", "temporal_analysis", 
        "multi_dimensional", "industry_analysis", "thematic_analysis"
    ] = Field(description="Query classification")
    sectors: List[str] = Field(default_factory=list, description="Industry sectors")
    keywords: List[str] = Field(default_factory=list, description="Key search terms")
    complexity_score: float = Field(ge=0.0, le=1.0, description="Query complexity")
    suggested_tickers: List[str] = Field(default_factory=list)
    selection_reason: str = ""  


class DocumentChunk(BaseModel):
    """A discrete text segment from a SEC filing, with full metadata"""

    content: str = Field(
        description="Extracted text content of the filing section or summary"
    )
    ticker: str = Field(
        description="Public stock ticker symbol of the company (e.g., 'AAPL')"
    )
    filing_type: str = Field(
        description="SEC form type of the document (e.g., '10-K', '4')"
    )
    filing_date: str = Field(
        description="Filing submission date in YYYY-MM-DD format"
    )
    section: Optional[str] = Field(
        default=None,
        description="Filing section or item name (e.g., 'Item 1A', 'Insider Filing')"
    )
    chunk_id: str = Field(
        description="Unique identifier for the chunk, used for traceability"
    )
    source_url: str = Field(
        description="Direct URL to the SEC-hosted filing document"
    )
    page_number: Optional[int] = Field(
        default=None,
        description="Page number in the original filing, if known"
    )
    confidence_score: float = Field(
        default=1.0,
        description="Confidence level in the quality and relevance of this chunk (0.0–1.0)"
    )

class Source(BaseModel):
    """Reference metadata for a cited SEC filing segment"""

    ticker: str = Field(
        description="Company stock ticker (e.g., 'MSFT')"
    )
    filing_type: str = Field(
        description="SEC form type of the source document (e.g., '10-K')"
    )
    filing_date: str = Field(
        description="Date the document was filed with the SEC (YYYY-MM-DD)"
    )
    section: Optional[str] = Field(
        default=None,
        description="Specific section or item name in the filing (e.g., 'Item 7')"
    )
    url: Optional[str] = Field(
        default=None,
        description="URL linking directly to the cited document or section"
    )
    chunk_id: Optional[str] = Field(
        default=None,
        description="Identifier for the originating chunk, if derived from chunk-based retrieval"
    )
    note: Optional[str] = Field(
        default=None,
        description="Brief extra context or label (e.g., insider name, transaction code, summary note)"
    )

class AnswerWithSources(BaseModel):
    answer: str = Field(
        default="", 
        description="The synthesized natural language answer to the user's question"
    )
    confidence_score: float = Field(
        default=0.5, ge=0.0, le=1.0,
        description="Confidence score of the answer based on source alignment and coverage"
    )
    sources: List['Source'] = Field(
        default_factory=list,
        description="Structured source references that support the answer"
    )
    citations: List[str] = Field(
        default_factory=list,
        description="List of inline citation tags used in the answer (e.g. ['C1', 'C2'])"
    )
    methodology: str = Field(
        default="",
        description="Brief summary of how the answer was generated (e.g., chunk IDs used, tool invoked)"
    )
    limitations: List[str] = Field(
        default_factory=list,
        description="Known limitations or disclaimers (e.g., missing data, only recent filings)"
    )
    companies_analyzed: List[str] = Field(
        default_factory=list,
        description="List of company tickers included in the analysis"
    )
    filing_types_used: List[str] = Field(
        default_factory=list,
        description="List of SEC form types used in the answer (e.g. ['10-K', '4'])"
    )
    time_period_covered: Optional[str] = Field(
        default=None,
        description="Time period the answer is based on (e.g., '2023', 'last 90 days')"
    )
    key_metrics: Dict[str, str] = Field(
        default_factory=dict,
        description="Any quantitative metrics extracted (e.g., revenue, growth rate)"
    )
    recommendations: List[str] = Field(
        default_factory=list,
        description="Suggested follow-ups based on gaps or findings in the answer"
    )
    tool_used: Optional[str] = Field(
        default=None,
        description="Name of the internal tool used (e.g., 'sec_tool(extract, ...') if applicable"
    )
    used_chunk_ids: List[str] = Field(
        default_factory=list,
        description="List of chunk IDs used to construct the answer"
    )

