# report_generator.py
import argparse
import datetime
from decimal import Decimal, ROUND_HALF_UP
import os
import sys
import io
import re
from dateutil.relativedelta import relativedelta

try:
    import parser
    from parser import Transaction
    from insights import calculate_summary_insights  # This should be insights_py_v8
except ImportError as e:
    print(f"Error importing parser or insights module: {e}")
    print("Please ensure parser.py and insights.py are in the same directory or accessible in your PYTHONPATH.")
    sys.exit(1)

try:
    from fpdf import FPDF
    from fpdf.enums import XPos, YPos
except ImportError:
    print("FPDF2 library not found. Please install it using: pip install fpdf2")
    sys.exit(1)

REPORTS_BASE_DIR = "reports"


def sanitize_filename(name: str) -> str:
    name = re.sub(r'[^\w\s-]', '', name)
    name = re.sub(r'[-\s]+', '_', name).strip('_')
    return name


def sanitize_text_for_pdf(text: str) -> str:
    if not isinstance(text, str):
        text = str(text)
    replacements = {
        '\u2018': "'", '\u2019': "'", '\u201C': '"', '\u201D': '"',
        '\u2026': "...", '\u2013': "-", '\u2014': "--", '\u00A0': " ",
    }
    for uni_char, ascii_char in replacements.items():
        text = text.replace(uni_char, ascii_char)
    return text.encode('latin-1', 'ignore').decode('latin-1')


def valid_date(s: str) -> datetime.date:
    try:
        return datetime.datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        msg = f"Not a valid date: '{s}'. Expected YYYY-MM-DD format."
        raise argparse.ArgumentTypeError(msg)


def generate_markdown_report(insights, output_filepath_base, report_title="Financial Report", date_range_str=""):
    full_report_title = f"{report_title}{' (' + date_range_str + ')' if date_range_str else ''} - {datetime.date.today().isoformat()}"
    report_str = f"# {full_report_title}\n\n"

    report_str += "## Executive Summary\n"
    exec_summary = insights.get('executive_summary', {})
    total_income_exec = Decimal(exec_summary.get('total_income', "0.00"))
    report_str += f"- **Total Income:** ${total_income_exec:.2f}\n"
    total_expenses_exec = Decimal(exec_summary.get('total_expenses', "0.00"))
    report_str += f"- **Total Expenses:** ${abs(total_expenses_exec):.2f}\n"
    if 'total_outstanding_invoices' in exec_summary:
        report_str += f"- **Total Outstanding Invoices:** ${Decimal(exec_summary['total_outstanding_invoices']):.2f}\n"
    if 'total_overdue_invoices' in exec_summary:
        report_str += f"- **Total Overdue Invoices:** ${Decimal(exec_summary['total_overdue_invoices']):.2f}\n"
    if 'top_client_by_revenue' in exec_summary:
        top_client = exec_summary['top_client_by_revenue']
        report_str += f"- **Top Client by Revenue:** {top_client['name']} (${Decimal(top_client['amount']):.2f})\n"
    if 'top_service_by_revenue' in exec_summary:
        top_service = exec_summary['top_service_by_revenue']
        report_str += f"- **Top Service/Item by Revenue:** {top_service['name']} (${Decimal(top_service['amount']):.2f})\n"
    if 'top_project_by_revenue' in exec_summary:  # New for Executive Summary
        top_project = exec_summary['top_project_by_revenue']
        report_str += f"- **Top Project by Revenue:** {top_project['name']} (${Decimal(top_project['amount']):.2f})\n"
    if 'best_rate_client' in exec_summary:
        best_rate_client = exec_summary['best_rate_client']
        report_str += f"- **Client with Best Average Rate:** {best_rate_client['name']} (${Decimal(best_rate_client['average_rate']):.2f}/unit or /hr)\n"
    if 'top_expense_category' in exec_summary:
        top_expense_cat = exec_summary['top_expense_category']
        report_str += f"- **Top Expense Category:** {top_expense_cat['name']} (${Decimal(top_expense_cat['amount']):.2f})\n"
    elif abs(total_expenses_exec) > 0:
        report_str += f"- No specific top expense category identified from categorized expenses.\n"
    report_str += "\n"

    comparison = insights.get('previous_period_comparison')
    if comparison:
        # ... (Previous Period Comparison Markdown as in v12) ...
        report_str += "## Comparison with Previous Period\n"
        changes = comparison.get('changes', {})
        income_comp = changes.get('total_income')
        if income_comp:
            report_str += f"- **Total Income:** ${income_comp['current']} (Prev: ${income_comp['previous']}"
            if income_comp['percent_change'] is not None:
                report_str += f", Change: {income_comp['percent_change']:.1f}%)"
            else:
                report_str += ", Prev was $0.00)"
            report_str += "\n"
        spending_comp = changes.get('total_spending')
        if spending_comp:
            current_abs_spending = abs(Decimal(spending_comp['current']));
            prev_abs_spending = abs(Decimal(spending_comp['previous']))
            report_str += f"- **Total Expenses:** ${current_abs_spending:.2f} (Prev: ${prev_abs_spending:.2f}"
            if spending_comp['percent_change'] is not None:
                report_str += f", Change: {spending_comp['percent_change']:.1f}%)"
            else:
                report_str += ", Prev was $0.00)"
            report_str += "\n"
        net_flow_comp = changes.get('net_flow_operational')
        if net_flow_comp:
            report_str += f"- **Net Operational Flow:** ${net_flow_comp['current']} (Prev: ${net_flow_comp['previous']}"
            if net_flow_comp['percent_change'] is not None:
                report_str += f", Change: {net_flow_comp['percent_change']:.1f}%)"
            else:
                report_str += ", Prev was $0.00)"
            report_str += "\n"
        report_str += "\n"

    report_str += "## Detailed Summary\n"
    # ... (Detailed Summary Markdown as in v12) ...
    total_income_val = insights.get('total_income', "0.00")
    if not isinstance(total_income_val, Decimal): total_income_val = Decimal(total_income_val)
    report_str += f"- Total Income (Overall): ${total_income_val:.2f}\n"
    total_expenses_val = insights.get('total_spending', "0.00")
    if not isinstance(total_expenses_val, Decimal): total_expenses_val = Decimal(total_expenses_val)
    report_str += f"- Total Expenses (Overall): ${abs(total_expenses_val):.2f}\n"
    net_savings_val = insights.get('net_flow_operational', "0.00")
    if not isinstance(net_savings_val, Decimal): net_savings_val = Decimal(net_savings_val)
    report_str += f"- Net Operational Flow: ${net_savings_val:.2f}\n\n"

    report_str += "## Payment Status Summary\n"
    # ... (Payment Status Markdown as in v12) ...
    payment_summary = insights.get('payment_status_summary', {})
    by_status = payment_summary.get('by_status', {})
    if by_status:
        for status, amount_str in sorted(
            by_status.items()): report_str += f"- **{status.capitalize()}**: ${Decimal(amount_str):.2f}\n"
    report_str += f"- **Total Outstanding (Sent/Viewed/Partial/Overdue):** ${Decimal(payment_summary.get('total_outstanding', '0.00')):.2f}\n"
    report_str += f"- **Total Overdue (subset of outstanding):** ${Decimal(payment_summary.get('total_overdue', '0.00')):.2f}\n"
    if not by_status and payment_summary.get('total_outstanding',
                                             '0.00') == '0.00': report_str += "- No specific payment status data found for this period.\n"
    report_str += "\n"

    report_str += "## Revenue by Client (Highest to Lowest)\n"
    # ... (Revenue by Client Markdown as in v12) ...
    revenue_by_client = insights.get('revenue_by_client')
    if revenue_by_client:
        sorted_revenue_by_client = sorted(revenue_by_client.items(), key=lambda item: Decimal(item[1]), reverse=True)
        for client, revenue_str_val in sorted_revenue_by_client:
            revenue_decimal = Decimal(revenue_str_val);
            report_str += f"- {client}: ${revenue_decimal:.2f}\n"
    else:
        report_str += "- No client-specific revenue found for this period.\n"
    report_str += "\n"

    report_str += "## Revenue by Service/Item (Highest to Lowest)\n"
    # ... (Revenue by Service Markdown as in v12) ...
    revenue_by_service = insights.get('revenue_by_service')
    if revenue_by_service:
        sorted_revenue_by_service = sorted(revenue_by_service.items(), key=lambda item: Decimal(item[1]), reverse=True)
        for service, revenue_str_val in sorted_revenue_by_service:
            revenue_decimal = Decimal(revenue_str_val);
            report_str += f"- {service}: ${revenue_decimal:.2f}\n"
    else:
        report_str += "- No service/item specific revenue found for this period.\n"
    report_str += "\n"

    # --- Revenue by Project Section (Markdown) ---
    report_str += "## Revenue by Project (Highest to Lowest)\n"
    revenue_by_project = insights.get('revenue_by_project')
    if revenue_by_project:
        sorted_revenue_by_project = sorted(
            revenue_by_project.items(),
            key=lambda item: Decimal(item[1]),  # Sort by revenue amount
            reverse=True
        )
        for project, revenue_str_val in sorted_revenue_by_project:
            revenue_decimal = Decimal(revenue_str_val)
            report_str += f"- {project}: ${revenue_decimal:.2f}\n"
    else:
        report_str += "- No project-specific revenue found for this period.\n"
    report_str += "\n"

    report_str += "## Client Rate Analysis\n"
    # ... (Client Rate Analysis Markdown as in v12) ...
    client_rate_analysis = insights.get('client_rate_analysis', {})
    rates_by_client = client_rate_analysis.get('rates_by_client')
    best_avg_rate_client_info = client_rate_analysis.get('best_average_rate_client')
    if best_avg_rate_client_info:
        report_str += f"**Recap - Client with Best Average Rate (this period):** {best_avg_rate_client_info['name']} (${Decimal(best_avg_rate_client_info['average_rate']):.2f}/unit or /hr)\n\n"
    if rates_by_client:
        report_str += "### Average Rates per Client (Highest to Lowest Average Rate, this period):\n"
        sorted_rates_by_client = sorted(rates_by_client.items(), key=lambda item: Decimal(item[1]['average_rate']),
                                        reverse=True)
        for client, rate_data in sorted_rates_by_client:
            avg_rate = Decimal(rate_data['average_rate']);
            max_r = Decimal(rate_data['max_rate']);
            min_r = Decimal(rate_data['min_rate']);
            num_tx = rate_data['num_transactions_with_rate']
            report_str += f"- **{client}**: Avg Rate: ${avg_rate:.2f} (Max: ${max_r:.2f}, Min: ${min_r:.2f}, from {num_tx} transactions with rate data)\n"
    else:
        report_str += "- No rate data found for clients in this period.\n"
    report_str += "\n"

    report_str += "## Spending by Category\n"
    # ... (Spending by Category Markdown as in v12) ...
    spending_by_category = insights.get('spending_by_category')
    if spending_by_category:
        actual_spending = {cat: Decimal(val) for cat, val in spending_by_category.items() if Decimal(val) < 0}
        if actual_spending:
            for category, total_decimal in sorted(actual_spending.items(), key=lambda item: item[
                1]): report_str += f"- {category}: ${abs(total_decimal):.2f}\n"
        else:
            report_str += "- No categorized spending found for this period.\n"
    else:
        report_str += "- No categorized spending found for this period.\n"
    report_str += "\n"

    md_filename = output_filepath_base + ".md"
    try:
        os.makedirs(os.path.dirname(md_filename), exist_ok=True)
        with open(md_filename, "w", encoding="utf-8") as f:
            f.write(report_str)
        print(f"Markdown report generated: {md_filename}")
    except IOError as e:
        print(f"Error writing Markdown file {md_filename}: {e}")
    return md_filename


def generate_pdf_report(insights, output_filepath_base, report_title="Financial Report", date_range_str=""):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    font_family = "Helvetica"
    effective_width = pdf.w - pdf.l_margin - pdf.r_margin

    full_report_title_pdf = f"{report_title}{' (' + date_range_str + ')' if date_range_str else ''}"
    sanitized_report_title = sanitize_text_for_pdf(full_report_title_pdf)

    pdf.set_font(font_family, "B", 18);
    pdf.cell(0, 10, sanitized_report_title, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
    pdf.set_font(font_family, "", 10);
    pdf.cell(0, 7, f"Report Date: {datetime.date.today().isoformat()}", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
    pdf.ln(5)

    pdf.set_font(font_family, "B", 14)
    pdf.cell(0, 10, "Executive Summary", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="L")
    pdf.set_font(font_family, "", 12)
    # ... (Executive Summary PDF from v12 - needs to be updated to include Top Project) ...
    exec_summary_pdf = insights.get('executive_summary', {})
    total_income_exec_pdf = Decimal(exec_summary_pdf.get('total_income', "0.00"))
    pdf.cell(0, 7, f"- Total Income: ${total_income_exec_pdf:.2f}", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="L")
    total_expenses_exec_pdf = Decimal(exec_summary_pdf.get('total_expenses', "0.00"))
    pdf.cell(0, 7, f"- Total Expenses: ${abs(total_expenses_exec_pdf):.2f}", new_x=XPos.LMARGIN, new_y=YPos.NEXT,
             align="L")
    if 'total_outstanding_invoices' in exec_summary_pdf:
        pdf.multi_cell(effective_width, 7,
                       f"- Total Outstanding Invoices: ${Decimal(exec_summary_pdf['total_outstanding_invoices']):.2f}",
                       new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="L")
    if 'total_overdue_invoices' in exec_summary_pdf:
        pdf.multi_cell(effective_width, 7,
                       f"- Total Overdue Invoices: ${Decimal(exec_summary_pdf['total_overdue_invoices']):.2f}",
                       new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="L")
    if 'top_client_by_revenue' in exec_summary_pdf:
        top_client_pdf = exec_summary_pdf['top_client_by_revenue']
        client_name_sanitized = sanitize_text_for_pdf(top_client_pdf['name'])
        pdf.multi_cell(effective_width, 7,
                       f"- Top Client by Revenue: {client_name_sanitized} (${Decimal(top_client_pdf['amount']):.2f})",
                       new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="L")
    if 'top_service_by_revenue' in exec_summary_pdf:
        top_service_pdf = exec_summary_pdf['top_service_by_revenue']
        service_name_sanitized = sanitize_text_for_pdf(top_service_pdf['name'])
        pdf.multi_cell(effective_width, 7,
                       f"- Top Service/Item by Revenue: {service_name_sanitized} (${Decimal(top_service_pdf['amount']):.2f})",
                       new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="L")
    if 'top_project_by_revenue' in exec_summary_pdf:  # New for Executive Summary PDF
        top_project_pdf = exec_summary_pdf['top_project_by_revenue']
        project_name_sanitized = sanitize_text_for_pdf(top_project_pdf['name'])
        pdf.multi_cell(effective_width, 7,
                       f"- Top Project by Revenue: {project_name_sanitized} (${Decimal(top_project_pdf['amount']):.2f})",
                       new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="L")
    if 'best_rate_client' in exec_summary_pdf:
        best_rate_client_pdf = exec_summary_pdf['best_rate_client']
        client_name_sanitized = sanitize_text_for_pdf(best_rate_client_pdf['name'])
        pdf.multi_cell(effective_width, 7,
                       f"- Client with Best Average Rate: {client_name_sanitized} (${Decimal(best_rate_client_pdf['average_rate']):.2f}/unit or /hr)",
                       new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="L")
    if 'top_expense_category' in exec_summary_pdf:
        top_expense_cat_pdf = exec_summary_pdf['top_expense_category']
        cat_name_sanitized = sanitize_text_for_pdf(top_expense_cat_pdf['name'])
        pdf.multi_cell(effective_width, 7,
                       f"- Top Expense Category: {cat_name_sanitized} (${Decimal(top_expense_cat_pdf['amount']):.2f})",
                       new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="L")
    elif abs(total_expenses_exec_pdf) > 0:
        pdf.cell(0, 7, f"- No specific top expense category identified from categorized expenses.", new_x=XPos.LMARGIN,
                 new_y=YPos.NEXT, align="L")
    pdf.ln(7)

    # ... (Previous Period Comparison PDF as in v12) ...
    comparison_pdf = insights.get('previous_period_comparison')
    if comparison_pdf:
        pdf.set_font(font_family, "B", 14)
        pdf.cell(0, 10, "Comparison with Previous Period", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="L")
        pdf.set_font(font_family, "", 12)
        changes_pdf = comparison_pdf.get('changes', {})
        income_comp_pdf = changes_pdf.get('total_income')
        if income_comp_pdf:
            text = f"- Total Income: ${income_comp_pdf['current']} (Prev: ${income_comp_pdf['previous']}"
            if income_comp_pdf['percent_change'] is not None:
                text += f", Change: {income_comp_pdf['percent_change']:.1f}%)"
            else:
                text += ", Prev was $0.00)"
            pdf.multi_cell(effective_width, 7, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="L")
        spending_comp_pdf = changes_pdf.get('total_spending')
        if spending_comp_pdf:
            current_abs_spending_pdf = abs(Decimal(spending_comp_pdf['current']));
            prev_abs_spending_pdf = abs(Decimal(spending_comp_pdf['previous']))
            text = f"- Total Expenses: ${current_abs_spending_pdf:.2f} (Prev: ${prev_abs_spending_pdf:.2f}"
            if spending_comp_pdf['percent_change'] is not None:
                text += f", Change: {spending_comp_pdf['percent_change']:.1f}%)"
            else:
                text += ", Prev was $0.00)"
            pdf.multi_cell(effective_width, 7, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="L")
        net_flow_comp_pdf = changes_pdf.get('net_flow_operational')
        if net_flow_comp_pdf:
            text = f"- Net Operational Flow: ${net_flow_comp_pdf['current']} (Prev: ${net_flow_comp_pdf['previous']}"
            if net_flow_comp_pdf['percent_change'] is not None:
                text += f", Change: {net_flow_comp_pdf['percent_change']:.1f}%)"
            else:
                text += ", Prev was $0.00)"
            pdf.multi_cell(effective_width, 7, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="L")
        pdf.ln(7)

    pdf.set_font(font_family, "B", 14);
    pdf.cell(0, 10, "Detailed Summary", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="L")
    # ... (Detailed Summary PDF as in v12) ...
    pdf.set_font(font_family, "", 12)
    total_income_val_pdf = insights.get('total_income', "0.00")
    if not isinstance(total_income_val_pdf, Decimal): total_income_val_pdf = Decimal(total_income_val_pdf)
    pdf.cell(0, 7, f"Total Income (Overall): ${total_income_val_pdf:.2f}", new_x=XPos.LMARGIN, new_y=YPos.NEXT,
             align="L")
    total_expenses_val_pdf = insights.get('total_spending', "0.00")
    if not isinstance(total_expenses_val_pdf, Decimal): total_expenses_val_pdf = Decimal(total_expenses_val_pdf)
    pdf.cell(0, 7, f"Total Expenses (Overall): ${abs(total_expenses_val_pdf):.2f}", new_x=XPos.LMARGIN, new_y=YPos.NEXT,
             align="L")
    net_savings_val_pdf = insights.get('net_flow_operational', "0.00")
    if not isinstance(net_savings_val_pdf, Decimal): net_savings_val_pdf = Decimal(net_savings_val_pdf)
    pdf.cell(0, 7, f"Net Operational Flow: ${net_savings_val_pdf:.2f}", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="L")
    pdf.ln(7)

    # ... (Payment Status, Revenue by Client, Revenue by Service PDF as in v12) ...
    pdf.set_font(font_family, "B", 14)
    pdf.cell(0, 10, "Payment Status Summary", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="L")
    pdf.set_font(font_family, "", 12)
    payment_summary_pdf = insights.get('payment_status_summary', {})
    by_status_pdf = payment_summary_pdf.get('by_status', {})
    if by_status_pdf:
        for status, amount_str in sorted(by_status_pdf.items()):
            status_sanitized = sanitize_text_for_pdf(status.capitalize())
            pdf.cell(0, 7, f"- {status_sanitized}: ${Decimal(amount_str):.2f}", new_x=XPos.LMARGIN, new_y=YPos.NEXT,
                     align="L")
    pdf.cell(0, 7,
             f"- Total Outstanding (Sent/Viewed/Partial/Overdue): ${Decimal(payment_summary_pdf.get('total_outstanding', '0.00')):.2f}",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="L")
    pdf.cell(0, 7,
             f"- Total Overdue (subset of outstanding): ${Decimal(payment_summary_pdf.get('total_overdue', '0.00')):.2f}",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="L")
    if not by_status_pdf and payment_summary_pdf.get('total_outstanding', '0.00') == '0.00':
        pdf.cell(0, 7, "- No specific payment status data found for this period.", new_x=XPos.LMARGIN, new_y=YPos.NEXT,
                 align="L")
    pdf.ln(7)

    pdf.set_font(font_family, "B", 14);
    pdf.cell(0, 10, "Revenue by Client (Highest to Lowest)", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="L")
    pdf.set_font(font_family, "", 12)
    revenue_by_client = insights.get('revenue_by_client')
    if revenue_by_client:
        sorted_revenue_by_client = sorted(revenue_by_client.items(), key=lambda item: Decimal(item[1]), reverse=True)
        for client, revenue_str_val in sorted_revenue_by_client:
            revenue_decimal = Decimal(revenue_str_val)
            sanitized_client = sanitize_text_for_pdf(client)
            pdf.cell(0, 7, f"- {sanitized_client}: ${revenue_decimal:.2f}", new_x=XPos.LMARGIN, new_y=YPos.NEXT,
                     align="L")
    else:
        pdf.cell(0, 7, "- No client-specific revenue found for this period.", new_x=XPos.LMARGIN, new_y=YPos.NEXT,
                 align="L")
    pdf.ln(7)

    pdf.set_font(font_family, "B", 14)
    pdf.cell(0, 10, "Revenue by Service/Item (Highest to Lowest)", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="L")
    pdf.set_font(font_family, "", 12)
    revenue_by_service_pdf = insights.get('revenue_by_service')
    if revenue_by_service_pdf:
        sorted_revenue_by_service_pdf = sorted(revenue_by_service_pdf.items(), key=lambda item: Decimal(item[1]),
                                               reverse=True)
        for service, revenue_str_val in sorted_revenue_by_service_pdf:
            revenue_decimal = Decimal(revenue_str_val)
            sanitized_service = sanitize_text_for_pdf(service)
            pdf.multi_cell(effective_width, 7, f"- {sanitized_service}: ${revenue_decimal:.2f}", new_x=XPos.LMARGIN,
                           new_y=YPos.NEXT, align="L")
    else:
        pdf.cell(0, 7, "- No service/item specific revenue found for this period.", new_x=XPos.LMARGIN, new_y=YPos.NEXT,
                 align="L")
    pdf.ln(7)

    # --- Revenue by Project Section (PDF) ---
    pdf.set_font(font_family, "B", 14)
    pdf.cell(0, 10, "Revenue by Project (Highest to Lowest)", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="L")
    pdf.set_font(font_family, "", 12)
    revenue_by_project_pdf = insights.get('revenue_by_project')
    if revenue_by_project_pdf:
        sorted_revenue_by_project_pdf = sorted(
            revenue_by_project_pdf.items(),
            key=lambda item: Decimal(item[1]),  # Sort by revenue amount
            reverse=True
        )
        for project, revenue_str_val in sorted_revenue_by_project_pdf:
            revenue_decimal = Decimal(revenue_str_val)
            sanitized_project = sanitize_text_for_pdf(project)
            pdf.multi_cell(effective_width, 7, f"- {sanitized_project}: ${revenue_decimal:.2f}", new_x=XPos.LMARGIN,
                           new_y=YPos.NEXT, align="L")
    else:
        pdf.cell(0, 7, "- No project-specific revenue found for this period.", new_x=XPos.LMARGIN, new_y=YPos.NEXT,
                 align="L")
    pdf.ln(7)

    pdf.set_font(font_family, "B", 14);
    pdf.cell(0, 10, "Client Rate Analysis", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="L")
    # ... (Client Rate Analysis PDF as in v12) ...
    client_rate_analysis = insights.get('client_rate_analysis', {})
    rates_by_client_pdf = client_rate_analysis.get('rates_by_client')
    best_avg_rate_client_info_pdf = client_rate_analysis.get('best_average_rate_client')
    if best_avg_rate_client_info_pdf:
        pdf.set_font(font_family, "B", 12)
        client_name_sanitized = sanitize_text_for_pdf(best_avg_rate_client_info_pdf['name'])
        rate_info_sanitized = f"Recap - Client with Best Avg Rate (this period): {client_name_sanitized} (${Decimal(best_avg_rate_client_info_pdf['average_rate']):.2f}/unit or /hr)"
        pdf.multi_cell(effective_width, 7, rate_info_sanitized, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="L")
        pdf.set_font(font_family, "", 12);
        pdf.ln(2)
    if rates_by_client_pdf:
        pdf.set_font(font_family, "BU", 12)
        pdf.cell(0, 7, "Average Rates per Client (Highest to Lowest Avg Rate, this period):", new_x=XPos.LMARGIN,
                 new_y=YPos.NEXT, align="L")
        pdf.set_font(font_family, "", 12)
        sorted_rates_by_client_pdf = sorted(rates_by_client_pdf.items(),
                                            key=lambda item: Decimal(item[1]['average_rate']), reverse=True)
        for client, rate_data in sorted_rates_by_client_pdf:
            avg_rate = Decimal(rate_data['average_rate']);
            max_r = Decimal(rate_data['max_rate']);
            min_r = Decimal(rate_data['min_rate']);
            num_tx = rate_data['num_transactions_with_rate']
            client_sanitized = sanitize_text_for_pdf(client)
            line_text = f"- {client_sanitized}: Avg Rate: ${avg_rate:.2f} (Max: ${max_r:.2f}, Min: ${min_r:.2f}, from {num_tx} txns with rate data)"
            pdf.multi_cell(effective_width, 7, line_text, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="L")
    else:
        pdf.cell(0, 7, "- No rate data found for clients in this period.", new_x=XPos.LMARGIN, new_y=YPos.NEXT,
                 align="L")
    pdf.ln(7)

    pdf.set_font(font_family, "B", 14);
    pdf.cell(0, 10, "Spending by Category", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="L")
    # ... (Spending by Category PDF as in v12) ...
    pdf.set_font(font_family, "", 12)
    spending_by_category = insights.get('spending_by_category')
    if spending_by_category:
        actual_spending_pdf = {cat: Decimal(val) for cat, val in spending_by_category.items() if Decimal(val) < 0}
        if actual_spending_pdf:
            for category, total_decimal in sorted(actual_spending_pdf.items(), key=lambda item: item[1]):
                category_sanitized = sanitize_text_for_pdf(category)
                pdf.cell(0, 7, f"- {category_sanitized}: ${abs(total_decimal):.2f}", new_x=XPos.LMARGIN,
                         new_y=YPos.NEXT, align="L")
        else:
            pdf.cell(0, 7, "- No categorized spending found for this period.", new_x=XPos.LMARGIN, new_y=YPos.NEXT,
                     align="L")
    else:
        pdf.cell(0, 7, "- No categorized spending found for this period.", new_x=XPos.LMARGIN, new_y=YPos.NEXT,
                 align="L")
    pdf.ln(7)

    pdf_filename = output_filepath_base + ".pdf"
    try:
        os.makedirs(os.path.dirname(pdf_filename), exist_ok=True)
        pdf.output(pdf_filename)
        print(f"PDF report generated: {pdf_filename}")
    except Exception as e:
        print(f"Error writing PDF file {pdf_filename}: {e}")
    return pdf_filename


def main():
    # ... (main function remains the same as report_generator_py_v12) ...
    parser_function_map = {
        "chase_checking": parser.parse_checking_csv, "chase_credit": parser.parse_credit_csv,
        "stripe": parser.parse_stripe_csv, "paypal": parser.parse_paypal_csv,
        "invoice": parser.parse_invoice_csv, "freshbooks": parser.parse_freshbooks_csv,
        "clockify": parser.parse_clockify_csv, "toggl": parser.parse_toggl_csv,
    }
    available_file_types = list(parser_function_map.keys())
    arg_parser = argparse.ArgumentParser(description="Generate financial reports from CSV files.")
    arg_parser.add_argument("csv_files", nargs="+", help="Paths to the input CSV files.")
    arg_parser.add_argument("--file-type", required=True, choices=available_file_types,
                            help=f"Type of CSV. Available: {', '.join(available_file_types)}")
    arg_parser.add_argument("-o", "--output", default="financial_report", help="Base name for output files.")
    arg_parser.add_argument("--title", default="Financial Report", help="Title for reports.")
    arg_parser.add_argument("--client-name", type=str, default=None, help="Client name for subdirectory.")
    arg_parser.add_argument("--start-date", type=valid_date, help="Start date for filtering transactions (YYYY-MM-DD).")
    arg_parser.add_argument("--end-date", type=valid_date, help="End date for filtering transactions (YYYY-MM-DD).")

    args = arg_parser.parse_args()

    if args.start_date and args.end_date and args.start_date > args.end_date:
        print("Error: Start date cannot be after end date.")
        sys.exit(1)

    all_transactions_raw = []
    dummy_user_id_for_cli = parser.DUMMY_CLI_USER_ID
    selected_parser_func = parser_function_map.get(args.file_type)

    if not selected_parser_func:
        print(f"Error: Unknown file type '{args.file_type}'. Available types are: {available_file_types}")
        sys.exit(1)
    output_dir = REPORTS_BASE_DIR
    if args.client_name:
        sanitized_client_name = sanitize_filename(args.client_name)
        output_dir = os.path.join(REPORTS_BASE_DIR, sanitized_client_name)
    os.makedirs(output_dir, exist_ok=True)

    output_name_suffix = ""
    date_range_display_str = ""
    if args.start_date and args.end_date:
        output_name_suffix = f"_{args.start_date.strftime('%Y%m%d')}-{args.end_date.strftime('%Y%m%d')}"
        date_range_display_str = f"{args.start_date.isoformat()} to {args.end_date.isoformat()}"
    elif args.start_date:
        output_name_suffix = f"_from_{args.start_date.strftime('%Y%m%d')}"
        date_range_display_str = f"From {args.start_date.isoformat()}"
    elif args.end_date:
        output_name_suffix = f"_until_{args.end_date.strftime('%Y%m%d')}"
        date_range_display_str = f"Until {args.end_date.isoformat()}"

    output_filename_base = sanitize_filename(args.output) + output_name_suffix
    output_filepath_base = os.path.join(output_dir, output_filename_base)

    print(f"Starting report generation for file type: {args.file_type}")
    if args.client_name:
        print(f"Reports for client: {args.client_name} in directory: {output_dir}")
    else:
        print(f"Reports will be saved in directory: {output_dir}")
    if date_range_display_str:
        print(f"Filtering transactions for period: {date_range_display_str}")

    for csv_file_path in args.csv_files:
        if not os.path.exists(csv_file_path):
            print(f"Warning: File not found, skipped: {csv_file_path}");
            continue
        print(f"Processing file: {csv_file_path}...")
        try:
            with open(csv_file_path, 'rb') as fb:
                file_content_bytes = fb.read()
            file_object_for_parser = io.BytesIO(file_content_bytes)
            base_filename = os.path.basename(csv_file_path)
            parsed_tx_list = selected_parser_func(user_id=dummy_user_id_for_cli, file_obj=file_object_for_parser,
                                                  filename=base_filename)
            if parsed_tx_list:
                print(f"Successfully parsed {len(parsed_tx_list)} transactions from {base_filename}.")
                all_transactions_raw.extend(parsed_tx_list)
            else:
                print(f"Warning: No transactions parsed from {base_filename}.")
            file_object_for_parser.close()
        except ValueError as ve:
            print(
                f"Error processing file {csv_file_path} ({args.file_type}): {ve}\n  Ensure CSV matches expected schema.")
        except Exception as e:
            print(f"Unexpected error processing file {csv_file_path} ({args.file_type}): {e}")

    if not all_transactions_raw:
        print("No transactions parsed from any file. Exiting.");
        return

    current_period_transactions = []
    previous_period_transactions_for_calc = None

    if args.start_date or args.end_date:
        for tx in all_transactions_raw:
            if tx.date:
                is_in_current_period = True
                if args.start_date and tx.date < args.start_date:
                    is_in_current_period = False
                if args.end_date and tx.date > args.end_date:
                    is_in_current_period = False
                if is_in_current_period:
                    current_period_transactions.append(tx)
        print(
            f"Filtered down to {len(current_period_transactions)} transactions for the current period based on date range.")

        if args.start_date and args.end_date:
            duration_days = (args.end_date - args.start_date).days
            prev_end_date = args.start_date - datetime.timedelta(days=1)
            prev_start_date = prev_end_date - datetime.timedelta(days=duration_days)

            print(f"Calculating previous period: {prev_start_date.isoformat()} to {prev_end_date.isoformat()}")
            previous_period_transactions_for_calc = []
            for tx in all_transactions_raw:
                if tx.date:
                    if prev_start_date <= tx.date <= prev_end_date:
                        previous_period_transactions_for_calc.append(tx)
            print(f"Found {len(previous_period_transactions_for_calc)} transactions for the previous period.")
    else:
        current_period_transactions = all_transactions_raw

    if not current_period_transactions:
        print("No transactions fall within the specified date range for the current period. Exiting.");
        return

    print(f"\nTotal transactions to be included in report (current period): {len(current_period_transactions)}")
    print("Calculating insights...")

    insights_data = calculate_summary_insights(
        current_period_transactions=current_period_transactions,
        previous_period_transactions=previous_period_transactions_for_calc
    )

    if not insights_data:
        print("Could not generate insights. Exiting.");
        return

    print("Generating reports...")
    generate_markdown_report(insights_data, output_filepath_base, args.title, date_range_display_str)
    generate_pdf_report(insights_data, output_filepath_base, args.title, date_range_display_str)
    print(f"\nReport generation complete. Files prefixed with: {output_filepath_base} (.md and .pdf)")


if __name__ == "__main__":
    main()
