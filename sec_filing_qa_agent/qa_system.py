import time
import re
from typing import List
from models import QueryAnalysis, DocumentChunk, AnswerWithSources, Source
from data_retriever import EnhancedSECDataRetriever
from query_agent import query_analyzer
from analysis_agent import financial_analyst
from company_resolver import CompanyResolver
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("sec_qa.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


class EnhancedSECQASystem:
    """Production-grade SEC Q&A system supporting multi-dimensional financial research"""

    def __init__(self):
        self.data_retriever = EnhancedSECDataRetriever()
        self.document_cache = {}
        self.company_resolver = CompanyResolver()
        self.missing_companies = []

        logger.info("System initialized with multi-ticker, temporal, and citation support.")

    #  extract used citation tags from model output
    @staticmethod
    def _parse_used_tags(text: str) -> list[int]:
        seen, order = set(), []
        for match in re.finditer(r'\[C(\d+)\]', text):
            cid = int(match.group(1))
            if cid not in seen:
                seen.add(cid)
                order.append(cid)
        return order

    #  renumber [C#] citations in order of appearance
    @staticmethod
    def _compact_renumber(text: str, used_ids: list[int]) -> tuple[str, dict[int, int]]:
        mapping = {old: new for new, old in enumerate(used_ids, start=1)}
        def replace(match):
            old_id = int(match.group(1))
            return f"[C{mapping[old_id]}]" if old_id in mapping else match.group(0)
        new_text = re.sub(r'\[C(\d+)\]', replace, text)
        return new_text, mapping

    def answer_question(self, question: str) -> AnswerWithSources:
        start = time.time()
        logger.info(f"\nQuestion: {question}")
        logger.info("=" * 80)

        try:
            #  Step 1: Query analysis
            query_analysis = query_analyzer.run_sync(question)
            if query_analysis.usage() and query_analysis.usage().has_values():
                logger.info(f"Total tokens for Query:{query_analysis.usage().total_tokens}")
            analysis = query_analysis.output if hasattr(query_analysis, 'output') else query_analysis
            logger.info(f"Query Type: {analysis.query_type}")
            logger.info(f"Tickers: {analysis.tickers}")
            logger.info(f"Time Periods: {analysis.time_periods}")
            logger.info(f"Document Types: {analysis.document_types}")
            logger.info(f"Complexity: {analysis.complexity_score:.2f}")

            #  Step 2: Determine target companies
            target_companies = self._determine_companies(analysis)
            logger.info(f"Target Companies: {target_companies}")

            #  Step 3: Retrieve document chunks
            document_chunks = self._retrieve_documents(target_companies, analysis)
            logger.info(f"Retrieved {len(document_chunks)} document chunks")

            #  Step 4: Perform analysis
            allowed_map, allowed_lines = {}, []
            for i, chunk in enumerate(document_chunks, start=1):
                allowed_map[i] = chunk
                allowed_lines.append(
                    f"- [C{i}] {chunk.ticker} {chunk.filing_type} {chunk.filing_date}, "
                    f"{chunk.section or 'Summary'} — {chunk.source_url}"
                )

            allowed_block = (
                "ALLOWED SOURCES (use only these, cite inline as [C#]):\n"
                + "\n".join(allowed_lines)
                + "\n\nCITATION RULES:\n"
                "- Only cite items above (do not mention forms not present).\n"
                "- Each Evidence bullet should include a [C#] tag.\n"
            )
            model_result = financial_analyst.run_sync(
                user_prompt=allowed_block + "\n" + question,
                deps=document_chunks
            )
            if model_result.usage() and model_result.usage().has_values():
                logger.info(f"Total tokens for Analysis: {model_result.usage().total_tokens}")
            answer = model_result.output if hasattr(model_result, 'output') else model_result

            if self.missing_companies:
                note = (
                    f"\nNote: No filings found for: {', '.join(self.missing_companies)}. "
                    "These companies were excluded due to missing or unavailable filings."
                )
                answer.answer += note

            #  Step 5: Normalize citations
            original_ids = self._parse_used_tags(answer.answer)
            answer.answer, id_map = self._compact_renumber(answer.answer, original_ids)

            answer.sources = []
            answer.used_chunk_ids = []

            for old_id in original_ids:
                chunk = allowed_map.get(old_id)
                if chunk:
                    answer.sources.append(Source(
                        ticker=chunk.ticker,
                        filing_type=chunk.filing_type,
                        filing_date=chunk.filing_date,
                        section=chunk.section or "Summary",
                        url=chunk.source_url,
                        chunk_id=chunk.chunk_id
                    ))
                    answer.used_chunk_ids.append(chunk.chunk_id)

            if original_ids:
                citation_lines = ["", "**Citations**"]
                for new_id, old_id in enumerate(original_ids, start=1):
                    c = allowed_map.get(old_id)
                    if c:
                        citation_lines.append(
                            f"[C{new_id}] {c.ticker} {c.filing_type} {c.filing_date}, "
                            f"{c.section or 'Summary'} — {c.source_url}"
                        )
                answer.answer += "\n" + "\n".join(citation_lines)

            #  Metadata
            answer.companies_analyzed = target_companies
            answer.filing_types_used = analysis.document_types
            answer.time_period_covered = ", ".join(analysis.time_periods) or "Recent filings"

            end = time.time()
            latency = end - start
            logger.info(f"Analysis completed in {latency:.1f} seconds")
            logger.info("=" * 80)
            logger.info(f"Total Tokens Used:{(query_analysis.usage().total_tokens if query_analysis.usage() and query_analysis.usage().has_values() else 0) + (model_result.usage().total_tokens if model_result.usage() and model_result.usage().has_values() else 0)}"
            )

            return answer

        except Exception as e:
            logger.error(f"Error during analysis: {e}")
            return AnswerWithSources(
                answer=f"Error: {str(e)}",
                sources=[],
                confidence_score=0.0,
                companies_analyzed=[],
                filing_types_used=[],
                limitations=["Internal error during analysis."],
            )


    #  Validate and normalize tickers using CompanyResolver
    def _validate_tickers(self, tickers: list[str]) -> list[str]:
        return [
            meta.ticker for t in (tickers or [])
            if (meta := self.company_resolver.resolve(t.upper()))
        ]

    #  Determine target companies from user input or fallback
    def _determine_companies(
        self,
        analysis: QueryAnalysis,
        top_k: int = 3,
        mode: str = "user_first"
    ) -> List[str]:
        user = self._validate_tickers(analysis.tickers)
        logger.info(f"User-specified tickers: {user}")
        logger.info(f"Suggested tickers: {analysis.suggested_tickers}")

        if user:
            return user[:top_k]  #  Return only validated user tickers

        suggested = self._validate_tickers(getattr(analysis, "suggested_tickers", []))
        if suggested:
            return suggested[:top_k]

        #  Fallback: default representative companies
        fallback_pool = ["AAPL", "MSFT", "JPM", "GOOGL", "AMZN", "META", "NVDA"]
        return self._validate_tickers(fallback_pool)[:top_k]

    #  Retrieve and cache SEC documents
    def _retrieve_documents(self, companies: List[str], analysis: QueryAnalysis) -> List[DocumentChunk]:
        all_chunks = []
        self.missing_companies = []

        date_from = None
        for period in analysis.time_periods or []:
            if period.isdigit() and len(period) == 4:
                date_from = f"{period}-01-01"
                break

        document_types = analysis.document_types or self._get_default_document_types(analysis)

        for company in companies:
            cache_key = f"{company}_{'-'.join(document_types)}_{date_from or 'recent'}"
            if cache_key in self.document_cache:
                all_chunks.extend(self.document_cache[cache_key])
            else:
                chunks = self.data_retriever.fetch_filings(
                    company, document_types, date_from, limit=3
                )
                if chunks:
                    self.document_cache[cache_key] = chunks
                    all_chunks.extend(chunks)
                else:
                    self.missing_companies.append(company)

        return all_chunks

    #  Infer default document types from query content
    def _get_default_document_types(self, analysis: QueryAnalysis) -> List[str]:
        keywords = " ".join(analysis.keywords).lower()

        if any(k in keywords for k in ["insider", "trading", "purchase", "sale"]):
            return ["4", "3", "5"]
        elif any(k in keywords for k in ["compensation", "executive", "salary", "pay"]):
            return ["DEF 14A"]
        elif any(k in keywords for k in ["acquisition", "merger", "material", "event"]):
            return ["8-K"]
        elif any(k in keywords for k in ["risk", "factor", "business"]):
            return ["10-K"]
        elif any(k in keywords for k in ["quarterly", "q1", "q2", "q3", "q4"]):
            return ["10-Q"]
        else:
            return ["10-K", "10-Q"]
