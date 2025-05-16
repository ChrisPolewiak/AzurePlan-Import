import pandas as pd
import json
import re
import sys
import locale
import datetime
import io
from datetime import date, timedelta, datetime
import warnings
warnings.simplefilter("ignore")
locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')

# Import data
def Import( filename, filedata ):
    print('filename:'+filename)
    if (filename.endswith('.csv') ):
        filedata_str = filedata.read().decode('utf-8')
        data = clean_bad_csv_lines( filedata_str )
        report = ImportFromCSV( data )
    return report

def remove_json_fields(line):
    # Znajdź wszystkie pola CSV wyglądające jak JSON i usuń je
    # Obsługuje wielokrotne JSON-y w jednej linii
    # Uwaga: zakłada, że JSON-y nie mają zagnieżdżeń {}
    return re.sub(r'(?<="){.*?}(?=")', '', line)

def clean_bad_csv_lines(csv_text):
    lines = csv_text.strip().splitlines()
    header = lines[0]
    cleaned_lines = [header]

    for i, line in enumerate(lines[1:], start=2):  # start=2 to reflect real line number
        try:
            pd.read_csv(io.StringIO(f"{header}\n{line}"), delimiter=';', quotechar='"', engine='python')
            cleaned_lines.append(line)  # linia OK
        except Exception as e:
            # print(f"⚠️  Błąd w linii {i}: {e}")
            # print(f"🧨 Treść linii: {line}")
            fixed_line = remove_json_fields(line)
            # print(f"✅ Poprawiona linia: {fixed_line}")
            cleaned_lines.append(fixed_line)

    return "\n".join(cleaned_lines)

# Import data from CSV
def ImportFromCSV( csvstring ):
    df = pd.read_csv(io.StringIO(csvstring), delimiter=';', quotechar='"', engine='python')
    return df.to_dict(orient='records')


# Calculate billing data
def Calculate( report ):
    billing={
        'meta':{
            'StartDate':'',
            'EndDate':''
            },
        'data':{
            'customers':{},
        }
    }
    subs={}
    for line in report:

        # Set Report Dates
        if billing['meta']['StartDate']=='':
            billing['meta']['StartDate'] = datetime.strptime( str(line['ChargeStartDate']), '%Y-%m-%d %H:%M:%S')
        if billing['meta']['EndDate']=='':
            billing['meta']['EndDate'] = datetime.strptime( str(line['ChargeEndDate']), '%Y-%m-%d %H:%M:%S')

        # Calculate Billing per Customer
        CustomerId = line['CustomerId'].lower()
        EntitlementId = line['EntitlementId'].lower()

        subs[EntitlementId]=1

        # Do not analyse empty lines
        if not pd.isna( CustomerId ) and not pd.isna( EntitlementId ):

            # Create new array for new Customer
            if not CustomerId in billing['data']['customers']:
                billing['data']['customers'][CustomerId]={
                    'CustomerName': line['CustomerName'],
                    'CustomerDomainName': line['CustomerDomainName'],
                    'CustomerCountry': line['CustomerCountry'],
                    'CustomerCost': float(),
                    'PartnerCost': float(),
                    'subscriptions':{}
                }

            if not EntitlementId in billing['data']['customers'][CustomerId]['subscriptions']:
                # print('Adding Entitlement:', EntitlementId)
                billing['data']['customers'][CustomerId]['subscriptions'][EntitlementId]={
                    'EntitlementName': line['EntitlementDescription'],
                    'CustomerCost': float(),
                    'PartnerCost': float()
                }

            UnitPrice = float( line['UnitPrice'].replace(',','.'))
            Quantity = float( line['Quantity'].replace(',','.'))
            BillingPreTaxTotal = float( line['BillingPreTaxTotal'].replace(',','.'))
            PCToBCExchangeRate = float( line['PCToBCExchangeRate'].replace(',','.'))
            EffectiveUnitPrice = float( line['EffectiveUnitPrice'].replace(',','.'))
            CustomerCost = UnitPrice * Quantity * PCToBCExchangeRate
            # CustomerCost = BillingPreTaxTotal * PCToBCExchangeRate
            PartnerCost = EffectiveUnitPrice * Quantity * PCToBCExchangeRate

            billing['data']['customers'][CustomerId]['subscriptions'][EntitlementId]['CustomerCost'] = billing['data']['customers'][CustomerId]['subscriptions'][EntitlementId]['CustomerCost'] + CustomerCost
            billing['data']['customers'][CustomerId]['subscriptions'][EntitlementId]['PartnerCost']  = billing['data']['customers'][CustomerId]['subscriptions'][EntitlementId]['PartnerCost'] + PartnerCost
            billing['data']['customers'][CustomerId]['CustomerCost'] = billing['data']['customers'][CustomerId]['CustomerCost'] + CustomerCost
            billing['data']['customers'][CustomerId]['PartnerCost']  = billing['data']['customers'][CustomerId]['PartnerCost'] + PartnerCost
            
            # print(
            #        'Customer:', CustomerId, 'Sub:', EntitlementId, 
            #        'UnitPrice:', UnitPrice,'\tQty:', Quantity,'\tPCT:', PCToBCExchangeRate, '\tEffective:', EffectiveUnitPrice,
            #        '\tCustomer:', CustomerCost,
            #        '\tCCostS:', round(billing['data']['customers'][CustomerId]['subscriptions'][EntitlementId]['CustomerCost'],2),
            #        '\tCCost:', round(billing['data']['customers'][CustomerId]['CustomerCost'],2),
            #        '\tPartner:', PartnerCost,
            #        '\tPCostS:', round(billing['data']['customers'][CustomerId]['subscriptions'][EntitlementId]['PartnerCost'],2),
            #        '\tPCost:', round(billing['data']['customers'][CustomerId]['PartnerCost'],2))

    # for CustomerId in billing['data']:
    #    print(CustomerId)
    #    billing['data']['customers'][CustomerId]['subscriptions'][EntitlementId]['CustomerCostSubscription'] = round( billing['data']['customers'][CustomerId]['subscriptions'][EntitlementId]['CustomerCostFloat'], 2)
    #    billing['data']['customers'][CustomerId]['subscriptions'][EntitlementId]['PartnerCostSubscription'] = round( billing['data']['customers'][CustomerId]['subscriptions'][EntitlementId]['PartnerCostFloat'], 2)

#    print(billing['data'][CustomerId]['CustomerCost'],billing['data'][CustomerId]['PartnerCost'])

    print('\n')
    print(subs)

    return billing

# Create TXT report
def ReportTXT( billing ):
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
            report += '{:9.2f}'.format( billing['data']['customers'][CustomerId]['subscriptions'][EntitlementId]['CustomerCost'] ) + ' EUR | '
            report += '{:9.2f}'.format( billing['data']['customers'][CustomerId]['subscriptions'][EntitlementId]['PartnerCost'] ) + ' EUR\n'
        report += '-----------------------------------------------------------------------------------------------------\n'
        report += '                                                                Total | '
        report += '{:9.2f}'.format( billing['data']['customers'][CustomerId]['CustomerCost'] ) + ' EUR | '
        report += '{:9.2f}'.format( billing['data']['customers'][CustomerId]['PartnerCost'] ) + ' EUR\n'
        report += '=====================================================================================================\n'
    return report

# Create JSON Report
def ReportJSON( billing ):
    json_object = json.dumps(billing, indent=4, sort_keys=True, default=str)
    return json_object

