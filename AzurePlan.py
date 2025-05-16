import json
import re
import sys
import locale
import datetime
import io
from datetime import date, timedelta, datetime
import warnings
import pandas as pd
import logging
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

warnings.simplefilter("ignore")
locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')

# Add logging to each function
def Import(filename, filedata):
    with tracer.start_as_current_span("AzurePlan.Import") as span:
        logging.info("Import function called with filename: %s", filename)
        span.set_attribute("import.filename", filename)
        try:
            if filename.endswith('.csv'):
                with tracer.start_as_current_span("read file"):
                    filedata_str = filedata.read().decode('utf-8')
                    span.set_attribute("import.file.size", len(filedata_str))

                with tracer.start_as_current_span("clean_bad_csv_lines"):
                    data = clean_bad_csv_lines(filedata_str)

                with tracer.start_as_current_span("ImportFromCSV"):
                    report = ImportFromCSV(data)
                    span.set_attribute("import.rows", len(report))

                logging.info("Import function completed")
                return report
        except Exception as e:
            span.record_exception(e)
            span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
            logging.exception("Exception during import")
            return None

def remove_json_fields(line):
    cleaned = re.sub(r'(?<="){.*?}(?=")', '', line)
    if cleaned != line:
        logging.debug("remove_json_fields modified line")
    return cleaned

def clean_bad_csv_lines(csv_text):
    with tracer.start_as_current_span("clean_bad_csv_lines") as span:
        logging.info("clean_bad_csv_lines called")

        lines = csv_text.strip().splitlines()
        header = lines[0]
        cleaned_lines = [header]

        fixed_count = 0
        total_lines = len(lines) - 1  # exclude header

        for i, line in enumerate(lines[1:], start=2):
            try:
                pd.read_csv(io.StringIO(f"{header}\n{line}"), delimiter=';', quotechar='"', engine='python')
                cleaned_lines.append(line)
            except Exception as e:
                # logging.warning("Error in line %d: %s", i, e)
                fixed_line = remove_json_fields(line)
                cleaned_lines.append(fixed_line)
                fixed_count += 1

        span.set_attribute("csv.lines_total", total_lines)
        span.set_attribute("csv.lines_fixed", fixed_count)
        span.set_attribute("csv.fix_rate", fixed_count / total_lines if total_lines else 0)                

        logging.info("clean_bad_csv_lines completed")
        return "\n".join(cleaned_lines)

def ImportFromCSV(csvstring):
    with tracer.start_as_current_span("ImportFromCSV") as span:
        logging.info("ImportFromCSV called")
        try:
            df = pd.read_csv(io.StringIO(csvstring), delimiter=';', quotechar='"', engine='python')
            span.set_attribute("csv.rows", len(df))
            span.set_attribute("csv.columns", len(df.columns))
            logging.info("ImportFromCSV completed")
            return df.to_dict(orient='records')
        except Exception as e:
            span.record_exception(e)
            span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
            logging.exception("Exception in ImportFromCSV")
            return []

def Calculate(report):
    with tracer.start_as_current_span("AzurePlan.Calculate") as span:
        logging.info("Calculate function called")

        billing = {
            'meta': {
                'StartDate': '',
                'EndDate': ''
            },
            'data': {
                'customers': {},
            }
        }

    subs = {}
    customers_count = 0
    subscriptions_count = 0
    total_customer_cost = 0.0
    total_partner_cost = 0.0
    
    for line in report:
        try:
            # Set Report Dates
            if not billing['meta']['StartDate']:
                billing['meta']['StartDate'] = datetime.strptime(str(line['ChargeStartDate']), '%Y-%m-%d %H:%M:%S')
            if not billing['meta']['EndDate']:
                billing['meta']['EndDate'] = datetime.strptime(str(line['ChargeEndDate']), '%Y-%m-%d %H:%M:%S')

            # Extract identifiers
            CustomerId = line['CustomerId'].lower()
            EntitlementId = line['EntitlementId'].lower()

            if pd.isna(CustomerId) or pd.isna(EntitlementId):
                continue

            subs[EntitlementId] = 1

            # Create customer block if missing
            if CustomerId not in billing['data']['customers']:
                billing['data']['customers'][CustomerId] = {
                    'CustomerName': line['CustomerName'],
                    'CustomerDomainName': line['CustomerDomainName'],
                    'CustomerCountry': line['CustomerCountry'],
                    'CustomerCost': 0.0,
                    'PartnerCost': 0.0,
                    'subscriptions': {}
                }

            # Create subscription block if missing
            customer = billing['data']['customers'][CustomerId]
            if EntitlementId not in customer['subscriptions']:
                customer['subscriptions'][EntitlementId] = {
                    'EntitlementName': line['EntitlementDescription'],
                    'CustomerCost': 0.0,
                    'PartnerCost': 0.0
                }
                subscriptions_count += 1

            # Calculate financials
            UnitPrice = float(str(line['UnitPrice']).replace(',', '.'))
            Quantity = float(str(line['Quantity']).replace(',', '.'))
            BillingPreTaxTotal = float(str(line['BillingPreTaxTotal']).replace(',', '.'))
            PCToBCExchangeRate = float(str(line['PCToBCExchangeRate']).replace(',', '.'))
            EffectiveUnitPrice = float(str(line['EffectiveUnitPrice']).replace(',', '.'))

            CustomerCost = UnitPrice * Quantity * PCToBCExchangeRate
            PartnerCost = EffectiveUnitPrice * Quantity * PCToBCExchangeRate

            # Aggregate
            customer['subscriptions'][EntitlementId]['CustomerCost'] += CustomerCost
            customer['subscriptions'][EntitlementId]['PartnerCost'] += PartnerCost
            customer['CustomerCost'] += CustomerCost
            customer['PartnerCost'] += PartnerCost

            total_customer_cost += CustomerCost
            total_partner_cost += PartnerCost

        except Exception as e:
            logging.warning("Skipping row due to error: %s", e)
            span.record_exception(e)

    # Final metrics for tracing
    span.set_attribute("billing.customers", customers_count)
    span.set_attribute("billing.subscriptions", subscriptions_count)
    span.set_attribute("billing.total_customer_cost", round(total_customer_cost, 4))
    span.set_attribute("billing.total_partner_cost", round(total_partner_cost, 4))
    logging.info("Calculate function completed")

    return billing

def ReportTXT(billing):
    logging.info("ReportTXT called")
    report = '=====================================================================================================\n'
    report += 'Azure Plan usage for period ' + str(billing['meta']['StartDate'].strftime('%Y-%m-%d')) + ' - ' + str(billing['meta']['EndDate'].strftime('%Y-%m-%d')) + '\n'
    report += '=====================================================================================================\n'
    for CustomerId in billing['data']['customers']:
        report += '\n\n'
        report += 'Customer Name: ' + str(billing['data']['customers'][CustomerId]['CustomerName']) + '\n'
        report += '    Tenant id: ' + str(CustomerId) + '\n'
        report += '  Domain name: ' + str(billing['data']['customers'][CustomerId]['CustomerDomainName']) + '\n'
        report += '-----------------------------------------------------------------------------------------------------\n'
        report += 'EntitlementId                       | Name                           | Customer Cost | Partner Cost \n'
        report += '-----------------------------------------------------------------------------------------------------\n'
        for EntitlementId in billing['data']['customers'][CustomerId]['subscriptions']:
            report += str(EntitlementId) + ' | '
            report += '{:30s}'.format(billing['data']['customers'][CustomerId]['subscriptions'][EntitlementId]['SubscriptionName']) + ' | '
            report += '{:9.2f}'.format(billing['data']['customers'][CustomerId]['subscriptions'][EntitlementId]['CustomerCost']) + ' EUR | '
            report += '{:9.2f}'.format(billing['data']['customers'][CustomerId]['subscriptions'][EntitlementId]['PartnerCost']) + ' EUR\n'
        report += '-----------------------------------------------------------------------------------------------------\n'
        report += '                                                                Total | '
        report += '{:9.2f}'.format(billing['data']['customers'][CustomerId]['CustomerCost']) + ' EUR | '
        report += '{:9.2f}'.format(billing['data']['customers'][CustomerId]['PartnerCost']) + ' EUR\n'
        report += '=====================================================================================================\n'
    logging.info("ReportTXT completed")
    return report

def ReportJSON(billing):
    logging.info("ReportJSON called")
    json_object = json.dumps(billing, indent=4, sort_keys=True, default=str)
    logging.info("ReportJSON completed")
    return json_object

