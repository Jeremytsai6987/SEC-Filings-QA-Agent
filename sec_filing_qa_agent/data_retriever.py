import os, time, requests, urllib.parse
from typing import List, Dict, Optional
from dotenv import load_dotenv
from models import DocumentChunk, QueryAnalysis
from datetime import datetime, timedelta

load_dotenv()
SEC_API_KEY = os.getenv("SEC_API_KEY")



class EnhancedSECDataRetriever:
    """
    Production-level SEC data retriever combining three modes:
    1. Targeted retrieval for known forms and sections
    2. General fallback retrieval across form types
    3. Low-traffic backup probe mode
    """

    def __init__(self):
        self.api_key = SEC_API_KEY
        self.search_url      = f"https://api.sec-api.io?token={self.api_key}"
        self.extractor_url   = "https://api.sec-api.io/extractor"
        self.insider_api_url = f"https://api.sec-api.io/insider-trading?token={self.api_key}"
    
    def _resolve_date_from(self, analysis: QueryAnalysis, default_days=180) -> str:
        for p in (analysis.time_periods or []):
            if p.isdigit() and len(p) == 4:
                return f"{p}-01-01"
        return (datetime.utcnow() - timedelta(days=default_days)).date().isoformat()

    # Smart Targeting Neccessary Files
    def fetch_targeted_filings(self, analysis: QueryAnalysis,
                            allow_default: bool = False,
                            fallback: str = "general_small",
                            max_targets: int = 6) -> List[DocumentChunk]:
        """Fetch filings based on targeted retrieval strategy."""

        strategy = self._determine_retrieval_strategy(analysis, allow_default=allow_default)
        chunks: List[DocumentChunk] = []
        for t in strategy['targets'][:max_targets]:   
            ticker, form = t['ticker'], t['filing_type']
            sections = t.get('sections', [])[:1]
            if form in ["3", "4", "5"]:
                chunks += self._fetch_insider_targeted(ticker, form, analysis)
            elif form in ["10-K", "10-Q"]:
                chunks += self._fetch_structured_targeted(ticker, form, sections, analysis)
            else:
                chunks += self._fetch_general_targeted(ticker, form, analysis)
            time.sleep(0.3)

        if chunks:
            return chunks
        if fallback == "general_small":
            return self._fetch_general_small_probe(analysis)
        return []


    def _determine_retrieval_strategy(self, analysis: QueryAnalysis, allow_default: bool = False) -> Dict:
        """Determine the targeted retrieval strategy based on query analysis."""
        s = {'description': '', 'reason': '', 'targets': []}
        kw = " ".join(analysis.keywords or []).lower()
        docset = set(d.upper() for d in (analysis.document_types or []))
        companies = (analysis.tickers[:2] if analysis.tickers else self._get_default_companies(analysis)[:2])

        insider_req = sorted((docset & {'3','4','5'}), key=lambda x: {'4':0,'3':1,'5':2}[x])
        if insider_req or ('insider' in kw or 'trading' in kw):
            s.update(description="Insider trading targeted", reason="explicit_form_or_keyword")
            forms_to_pull = insider_req or ['4']  
            for c in companies[:2]:
                for f in forms_to_pull:
                    s['targets'].append({'ticker': c, 'filing_type': f, 'sections': []})
            return s
        
        if '10-K' in docset or ('risk' in kw or 'factor' in kw):
            s.update(description="10-K Risk factors (Item 1A)", reason="explicit_form_or_keyword")
            for c in companies[:2]:
                s['targets'].append({'ticker': c, 'filing_type': '10-K', 'sections': ['1A']})
            return s

        if '10-Q' in docset or ('md&a' in kw or 'management discussion' in kw):
            s.update(description="10-Q MD&A (part1item2)", reason="explicit_form_or_keyword")
            for c in companies[:2]:
                s['targets'].append({'ticker': c, 'filing_type': '10-Q', 'sections': ['part1item2']})
            return s

        if 'DEF 14A' in docset or ('compensation' in kw or 'proxy' in kw):
            s.update(description="Proxy / compensation", reason="explicit_form_or_keyword")
            for c in companies[:2]:
                s['targets'].append({'ticker': c, 'filing_type': 'DEF 14A', 'sections': []})
            return s

        #  Multiple tickers with 10-K Item 1A
        if getattr(analysis, 'query_type', None) == 'multi_ticker_comparison':
            s.update(description="Multi-company comparison (10-K 1A)", reason="query_type")
            for c in companies:
                s['targets'].append({'ticker': c, 'filing_type': '10-K', 'sections': ['1A']})
            return s

        # Industry analysis with no specific form
        if allow_default:
            s.update(description="Default targeted (single 10-K 1A)", reason="default")
            s['targets'].append({'ticker': companies[0], 'filing_type': '10-K', 'sections': ['1A']})
        else:
            s.update(description="No matching rule", reason="no_match")
        return s

    def _get_default_companies(self, analysis: QueryAnalysis) -> List[str]:
        kw = " ".join(analysis.keywords or []).lower()
        if "financial" in kw: return ["JPM"]
        if "healthcare" in kw: return ["JNJ"]
        return ["AAPL"]

    # Targeted fetchers
    def _fetch_insider_targeted(self, ticker: str, form_type: str, analysis: QueryAnalysis) -> List[DocumentChunk]:
        """Fetch targeted insider trading filings (Forms 3/4/5) for a specific ticker."""
        chunks: List[DocumentChunk] = []
        try:
            date_from = self._resolve_date_from(analysis)
            q = f'issuer.tradingSymbol:{ticker} AND documentType:{form_type} AND filedAt:[{date_from} TO *]'
            payload = {"query": {"query_string": {"query": q}}, "from": "0", "size": "1", "sort": [{"filedAt":{"order":"desc"}}]}
            r = requests.post(self.insider_api_url, json=payload, timeout=30, headers={'Content-Type': 'application/json'})
            if r.status_code != 200:
                return chunks
            data = r.json()
            txs = data.get('transactions', [])
            if not txs: return chunks
            filing = txs[0]

            person = (filing.get('reportingOwner') or {}).get('name', 'Unknown Person')
            filed = filing.get('filedAt','')[:10]
            lines = [f"Recent Insider Trading - {ticker}", f"Person: {person}", f"Filed: {filed}", ""]
            total = 0.0
            nd = (filing.get('nonDerivativeTable') or {}).get('transactions', [])
            for t in nd[:2]:
                amt = t.get('amounts', {}) or {}
                try:
                    sh = float(amt.get('shares', 0) or 0)
                    px = float(amt.get('pricePerShare', 0) or 0)
                except: 
                    continue
                val = sh * px
                total += val
                act = "Acquired" if amt.get('acquiredDisposedCode')=='A' else "Disposed"
                lines.append(f"- {act} {sh:,.0f} @ ${px:.2f} (${val:,.0f})")
            if total>0: lines.append(f"\nTotal Value: ${total:,.0f}")
            content = "\n".join(lines)
            if content:
                chunks.append(DocumentChunk(
                    content=content[:1200],
                    ticker=ticker,
                    filing_type=form_type,
                    filing_date=filed,
                    section=f"Insider Filing - {person}",
                    chunk_id=f"{ticker}_{form_type}_targeted",
                    source_url=filing.get('linkToFilingDetails',''),
                    confidence_score=1.0
                ))
            return chunks
        except Exception:
            return chunks

    def _fetch_structured_targeted(self, ticker: str, form_type: str, sections: List[str], analysis: 'QueryAnalysis') -> List['DocumentChunk']:
        """Fetch structured filings like 10-K/10-Q with specific sections."""
        chunks: List[DocumentChunk] = []
        try:
            q = f'ticker:{ticker} AND formType:"{form_type}"'
            payload = {"query":{"query_string":{"query":q}}, "from":0, "size":1, "sort":[{"filedAt":{"order":"desc"}}]}
            r = requests.post(self.search_url, json=payload, timeout=30)
            if r.status_code != 200: return chunks
            filings = (r.json() or {}).get("filings", [])
            if not filings: return chunks
            filing = filings[0]
            link = filing.get("linkToHtml") or filing.get("linkToTxt")
            if not link or not sections: return chunks

            sec = sections[0]
            params = {"url": link, "item": sec, "type":"text", "token": self.api_key}
            full_url = self.extractor_url + "?" + urllib.parse.urlencode(params, safe=":/")
            rr = requests.get(full_url, timeout=60)
            if rr.status_code != 200: return chunks
            text = (rr.text or "").strip()
            if len(text) < 200: return chunks

            if len(text) > 1500: text = text[:1500] + "..."
            chunks.append(DocumentChunk(
                content=text,
                ticker=ticker,
                filing_type=form_type,
                filing_date=filing.get("filedAt","")[:10],
                section=f"Item {sec}",
                chunk_id=f"{ticker}_{form_type}_{sec}_targeted",
                source_url=link,
                confidence_score=1.0
            ))
            return chunks
        except Exception:
            return chunks

    def _fetch_general_targeted(self, ticker: str, form_type: str, analysis: 'QueryAnalysis') -> List['DocumentChunk']:
        """Fetch general filings like 8-K/DEF 14A with no specific sections."""
        chunks: List[DocumentChunk] = []
        try:
            q = f'ticker:{ticker} AND formType:"{form_type}"'
            payload = {"query":{"query_string":{"query":q}}, "from":0, "size":1, "sort":[{"filedAt":{"order":"desc"}}]}
            r = requests.post(self.search_url, json=payload, timeout=30)
            if r.status_code != 200: return chunks
            filings = (r.json() or {}).get("filings", [])
            if not filings: return chunks
            f = filings[0]
            company = f.get('companyName','Unknown Company')
            date = f.get('filedAt','')[:10]
            desc = f.get('description', f'{form_type} filing')[:180]
            content = f"""{form_type} Filing - {company}
Date: {date}
Summary: {desc}...

This filing contains material information relevant to the query."""
            chunks.append(DocumentChunk(
                content=content,
                ticker=ticker,
                filing_type=form_type,
                filing_date=date,
                section=self._section_name(form_type),
                chunk_id=f"{ticker}_{form_type}_targeted",
                source_url=f.get('linkToFilingDetails',''),
                confidence_score=0.8
            ))
            return chunks
        except Exception:
            return chunks

    def _fetch_general_small_probe(self, analysis: QueryAnalysis) -> List[DocumentChunk]:
        """Fallback to small probe for general queries without specific forms."""
        cands = (analysis.tickers or self._get_default_companies(analysis))[:1]
        form  = (analysis.document_types[:1] or ["10-K"])[0]
        chunks: List[DocumentChunk] = []
        for c in cands:
            if form in ["10-K","10-Q"]:
                sec = ["1A"] if form=="10-K" else ["part1item2"]
                chunks += self._fetch_structured_targeted(c, form, sec, analysis)
            else:
                chunks += self._fetch_general_targeted(c, form, analysis)
        return chunks[:2]

    def _section_name(self, form_type: str) -> str:
        return {
            "8-K":"Material Event",
            "DEF 14A":"Proxy Statement",
            "3":"Initial Statement of Ownership",
            "4":"Statement of Changes in Ownership",
            "5":"Annual Statement of Ownership",
        }.get(form_type, f"{form_type} Filing")

    #  General retrieval methods
    def fetch_filings(self, ticker: str, filing_types: List[str],
                      date_from: Optional[str] = None, limit: int = 3) -> List[DocumentChunk]:
        """
        Fetch filings for a specific ticker across multiple form types.
        Supports insider forms (3/4/5), structured filings (10-K/10-Q),
        and general filings (8-K/DEF 14A).
        """
        all_chunks: List[DocumentChunk] = []

        for form in filing_types:
            print(f"   Fetching {form} filings for {ticker}...")
            if form in ["3", "4", "5"]:
                chunks = self._fetch_insider_filings(ticker, form, date_from, limit)
            elif form in ["10-K", "10-Q"]:
                chunks = self._fetch_structured_filings(ticker, form, date_from, limit)
            else:
                chunks = self._fetch_general_filings(ticker, form, date_from, limit)

            all_chunks.extend(chunks)
            time.sleep(0.5)  # rate limit

        return all_chunks

    def _fetch_insider_filings(self, ticker: str, form_type: str,
                               date_from: Optional[str], limit: int) -> List[DocumentChunk]:
        """ Fetch insider trading filings (Forms 3/4/5) for a specific ticker. When no filings found, fallback to general search. """
        chunks: List[DocumentChunk] = []
        try:
            query_string = f'issuer.tradingSymbol:{ticker} AND documentType:{form_type}'
            if date_from:
                query_string += f' AND filedAt:[{date_from} TO *]'

            payload = {
                "query": {"query_string": {"query": query_string}},
                "from": "0",
                "size": str(min(limit, 10)),
                "sort": [{"filedAt": {"order": "desc"}}]
            }
            print(f"   Insider API query: {query_string}")
            response = requests.post(self.insider_api_url, json=payload, timeout=30,
                                     headers={'Content-Type': 'application/json'})

            if response.status_code == 200:
                data = response.json()
                transactions = data.get('transactions', [])
                if transactions:
                    chunks = self._process_insider_filings(transactions, ticker, form_type)
                else:
                    print(f"No insider transactions found for {ticker}")
            else:
                print(f"Insider API error: {response.status_code} - fallback to general search")
                chunks = self._fetch_general_filings(ticker, form_type, date_from, limit)

        except Exception as e:
            print(f"Error fetching insider data: {e} - fallback to general search")
            chunks = self._fetch_general_filings(ticker, form_type, date_from, limit)

        return chunks

    def _process_insider_filings(self, filings: List[Dict],
                                 ticker: str, form_type: str) -> List[DocumentChunk]:
        """Process insider filings into DocumentChunk objects."""
        chunks: List[DocumentChunk] = []
        if not filings:
            return chunks

        for filing in filings[:5]:  
            try:
                content = self._format_insider_filing(filing, ticker)
                if content and len(content) > 50:
                    person_name = "Unknown Person"
                    if isinstance(filing.get('reportingOwner'), dict):
                        person_name = filing['reportingOwner'].get('name', 'Unknown Person')

                    filing_date = filing.get('filedAt', '')[:10]
                    chunk = DocumentChunk(
                        content=content,
                        ticker=ticker,
                        filing_type=form_type,
                        filing_date=filing_date,
                        section=f"Insider Filing - {person_name}",
                        chunk_id=f"{ticker}_{form_type}_{filing.get('accessionNumber', str(hash(content))[:8])}",
                        source_url=filing.get('linkToFilingDetails', ''),
                        confidence_score=1.0
                    )
                    chunks.append(chunk)
            except Exception as e:
                print(f"Error processing insider filing: {e}")
                continue
        return chunks

    def _format_insider_filing(self, filing: Dict, ticker: str) -> str:
        """Format the content of an insider trading filing into a readable string."""
        if not filing:
            return ""
        try:
            person_name = "Unknown Person"
            if isinstance(filing.get('reportingOwner'), dict):
                person_name = filing['reportingOwner'].get('name', 'Unknown Person')

            filing_date = filing.get('filedAt', 'Unknown')[:10]
            document_type = filing.get('documentType', 'Unknown')
            period_of_report = filing.get('periodOfReport', 'Unknown')[:10]

            lines = [
                f"SEC Form {document_type} - Insider Trading Report",
                f"Company: {ticker}",
                f"Reporting Person: {person_name}",
                f"Filing Date: {filing_date}",
                f"Period of Report: {period_of_report}",
                ""
            ]

            nd = (filing.get('nonDerivativeTable') or {}).get('transactions', [])
            if nd:
                lines.append("Non-Derivative Securities Transactions:")
                total_value, count = 0.0, 0
                for t in nd:
                    try:
                        amounts = t.get('amounts', {}) or {}
                        shares = float(amounts.get('shares', 0) or 0)
                        px = float(amounts.get('pricePerShare', 0) or 0)
                        acq_disp = amounts.get('acquiredDisposedCode', 'Unknown')
                        tx_val = shares * px
                        total_value += tx_val; count += 1
                        coding = t.get('coding', {}) or {}
                        code = coding.get('code', 'Unknown')
                        action = "Acquired" if acq_disp == 'A' else "Disposed" if acq_disp == 'D' else acq_disp
                        date = (t.get('transactionDate') or '')[:10]
                        sec_title = t.get('securityTitle', 'Common Stock')
                        lines.append(f"  - {date}: {action} {shares:,.0f} {sec_title} @ ${px:.2f} (Code: {code})")
                        if tx_val > 0:
                            lines.append(f"    Transaction Value: ${tx_val:,.0f}")
                    except Exception as e:
                        lines.append(f"  - Transaction processing error: {str(e)[:50]}")
                if count > 0:
                    lines.extend([
                        "",
                        "Transaction Summary:",
                        f"  - Number of Transactions: {count}",
                        f"  - Total Transaction Value: ${total_value:,.0f}",
                        ""
                    ])

            if (filing.get('derivativeTable') or {}).get('transactions'):
                lines.append("Note: This filing also includes derivative securities transactions.")
            return "\n".join(lines)
        except Exception as e:
            return f"Insider filing for {ticker} - Content processing error: {str(e)[:100]}"

    def _fetch_structured_filings(self, ticker: str, form_type: str,
                                  date_from: Optional[str], limit: int) -> List[DocumentChunk]:
        """ Fetch structured filings like 10-K/10-Q with specific sections."""
        chunks: List[DocumentChunk] = []
        try:
            query = f'ticker:{ticker} AND formType:"{form_type}"'
            if date_from:
                query += f' AND filedAt:[{date_from} TO *]'
            payload = {
                "query": {"query_string": {"query": query}},
                "from": 0, "size": limit,
                "sort": [{"filedAt": {"order": "desc"}}]
            }
            r = requests.post(self.search_url, json=payload, timeout=30)
            if r.status_code != 200:
                print(f"Search API error: {r.status_code}")
                return chunks
            data = r.json()
            filings = data.get("filings", [])
            if not filings:
                print(f"No {form_type} filings found")
                return chunks

            print(f"Found {len(filings)} {form_type} filings")
            items = self._get_extraction_items(form_type)

            for filing in filings:
                link = filing.get("linkToHtml") or filing.get("linkToTxt")
                if not link:
                    continue
                for item_code in items:
                    content = self._call_item_extractor(link, item_code)
                    if content and len(content) > 200:
                        chunks.append(DocumentChunk(
                            content=content,
                            ticker=ticker,
                            filing_type=form_type,
                            filing_date=filing.get("filedAt", "")[:10],
                            section=f"Item {item_code}",
                            chunk_id=f"{ticker}_{form_type}_{filing.get('accessionNo','unknown')}_{item_code}",
                            source_url=link,
                            confidence_score=1.0
                        ))
                time.sleep(0.7)
        except Exception as e:
            print(f"Error fetching structured filings: {e}")
        return chunks

    def _get_extraction_items(self, form_type: str) -> List[str]:
        if form_type == "10-K":
            return ["1", "1A", "7"]      # Business / Risk Factors / MD&A
        if form_type == "10-Q":
            return ["part1item2"]        # MD&A
        return []

    def _call_item_extractor(self, filing_url: str, item_code: str) -> str:
        params = {"url": filing_url, "item": item_code, "type": "text", "token": self.api_key}
        full_url = self.extractor_url + "?" + urllib.parse.urlencode(params, safe=":/")
        try:
            r = requests.get(full_url, timeout=60)
            if r.status_code == 200:
                return (r.text or "").strip()
            else:
                print(f"Item extractor {item_code} → {r.status_code}")
                return ""
        except Exception as e:
            print(f"Item extractor error: {e}")
            return ""

    def _fetch_general_filings(self, ticker: str, form_type: str,
                               date_from: Optional[str], limit: int) -> List[DocumentChunk]:
        """ Fetch general filings like 8-K/DEF 14A with no specific sections."""
        chunks: List['DocumentChunk'] = []
        try:
            query = f'ticker:{ticker} AND formType:"{form_type}"'
            if date_from:
                query += f' AND filedAt:[{date_from} TO *]'
            payload = {
                "query": {"query_string": {"query": query}},
                "from": 0, "size": limit,
                "sort": [{"filedAt": {"order": "desc"}}]
            }
            r = requests.post(self.search_url, json=payload, timeout=30)
            if r.status_code != 200:
                print(f"Search API error: {r.status_code}")
                return chunks

            filings = (r.json() or {}).get("filings", [])
            print(f"Found {len(filings)} {form_type} filings via general search")
            for f in filings:
                try:
                    content = self._get_filing_summary(f, form_type)
                    if content and len(content) > 50:
                        chunks.append(DocumentChunk(
                            content=content,
                            ticker=ticker,
                            filing_type=form_type,
                            filing_date=f.get("filedAt", "")[:10],
                            section=self._section_name(form_type),
                            chunk_id=f"{ticker}_{form_type}_{f.get('accessionNo', 'unknown')}",
                            source_url=f.get("linkToFilingDetails", ""),
                            confidence_score=0.8
                        ))
                except Exception as e:
                    print(f"Error processing filing: {e}")
                    continue
        except Exception as e:
            print(f"Error fetching general filings: {e}")
        return chunks

    def _get_filing_summary(self, filing: Dict, form_type: str) -> str:
        """ Generate a summary for a general filing based on its type."""
        try:
            company_name = filing.get('companyName', 'Unknown Company')
            filing_date = filing.get('filedAt', 'Unknown')[:10]
            description = filing.get('description', f'{form_type} filing')

            lines = [
                f"{form_type} Filing Summary",
                f"Company: {company_name}",
                f"Filing Date: {filing_date}",
                f"Description: {description}",
                ""
            ]
            if form_type == "8-K":
                lines.append("This is a Current Report (8-K) that discloses material corporate events.")
                if 'Item' in description:
                    lines.append("Items reported are indicated in the description above.")
            elif form_type == "DEF 14A":
                lines.append("This is a Definitive Proxy Statement, typically containing:")
                lines.append("- Executive compensation information")
                lines.append("- Board of directors information")
                lines.append("- Shareholder voting matters")
            elif form_type in ["3", "4", "5"]:
                lines.append(f"This is a Form {form_type} insider trading report.")
                lines.append("Contains information about securities transactions by company insiders.")

            if 'cik' in filing:
                lines.append(f"Company CIK: {filing['cik']}")
            if 'linkToFilingDetails' in filing:
                lines.append(f"Filing URL: {filing['linkToFilingDetails']}")

            return "\n".join(lines)
        except Exception as e:
            return f"{form_type} filing summary - Processing error: {str(e)[:100]}"
