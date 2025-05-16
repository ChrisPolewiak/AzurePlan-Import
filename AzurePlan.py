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

warnings.simplefilter("ignore")
locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')

# Add logging to each function
def Import(filename, filedata):
    logging.info("Import function called with filename: %s", filename)
    print('filename:' + filename)
    if filename.endswith('.csv'):
        filedata_str = filedata.read().decode('utf-8')
        data = clean_bad_csv_lines(filedata_str)
        report = ImportFromCSV(data)
    logging.info("Import function completed")
    return report

def remove_json_fields(line):
#    logging.debug("remove_json_fields called")
    return re.sub(r'(?<="){.*?}(?=")', '', line)

def clean_bad_csv_lines(csv_text):
    logging.info("clean_bad_csv_lines called")
    lines = csv_text.strip().splitlines()
    header = lines[0]
    cleaned_lines = [header]

    for i, line in enumerate(lines[1:], start=2):
        try:
            pd.read_csv(io.StringIO(f"{header}\n{line}"), delimiter=';', quotechar='"', engine='python')
            cleaned_lines.append(line)
        except Exception as e:
            logging.warning("Error in line %d: %s", i, e)
            fixed_line = remove_json_fields(line)
            cleaned_lines.append(fixed_line)

    logging.info("clean_bad_csv_lines completed")
    return "\n".join(cleaned_lines)

def ImportFromCSV(csvstring):
    logging.info("ImportFromCSV called")
    df = pd.read_csv(io.StringIO(csvstring), delimiter=';', quotechar='"', engine='python')
    logging.info("ImportFromCSV completed")
    return df.to_dict(orient='records')

def Calculate(report):
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
    for line in report:
        # Set Report Dates
        if billing['meta']['StartDate'] == '':
            billing['meta']['StartDate'] = datetime.strptime(str(line['ChargeStartDate']), '%Y-%m-%d %H:%M:%S')
        if billing['meta']['EndDate'] == '':
            billing['meta']['EndDate'] = datetime.strptime(str(line['ChargeEndDate']), '%Y-%m-%d %H:%M:%S')

        # Calculate Billing per Customer
        CustomerId = line['CustomerId'].lower()
        EntitlementId = line['EntitlementId'].lower()

        subs[EntitlementId] = 1

        if not pd.isna(CustomerId) and not pd.isna(EntitlementId):
            if CustomerId not in billing['data']['customers']:
                billing['data']['customers'][CustomerId] = {
                    'CustomerName': line['CustomerName'],
                    'CustomerDomainName': line['CustomerDomainName'],
                    'CustomerCountry': line['CustomerCountry'],
                    'CustomerCost': float(),
                    'PartnerCost': float(),
                    'subscriptions': {}
                }

            if EntitlementId not in billing['data']['customers'][CustomerId]['subscriptions']:
                billing['data']['customers'][CustomerId]['subscriptions'][EntitlementId] = {
                    'EntitlementName': line['EntitlementDescription'],
                    'CustomerCost': float(),
                    'PartnerCost': float()
                }

            UnitPrice = float(line['UnitPrice'].replace(',', '.'))
            Quantity = float(line['Quantity'].replace(',', '.'))
            BillingPreTaxTotal = float(line['BillingPreTaxTotal'].replace(',', '.'))
            PCToBCExchangeRate = float(line['PCToBCExchangeRate'].replace(',', '.'))
            EffectiveUnitPrice = float(line['EffectiveUnitPrice'].replace(',', '.'))
            CustomerCost = UnitPrice * Quantity * PCToBCExchangeRate
            PartnerCost = EffectiveUnitPrice * Quantity * PCToBCExchangeRate

            billing['data']['customers'][CustomerId]['subscriptions'][EntitlementId]['CustomerCost'] += CustomerCost
            billing['data']['customers'][CustomerId]['subscriptions'][EntitlementId]['PartnerCost'] += PartnerCost
            billing['data']['customers'][CustomerId]['CustomerCost'] += CustomerCost
            billing['data']['customers'][CustomerId]['PartnerCost'] += PartnerCost

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

