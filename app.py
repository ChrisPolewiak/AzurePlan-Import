# 
# Written By: Chris Polewiak
# Website:	https://github.com/ChrisPolewiak/azure-toolkit/tree/master/AzurePlan-Import

from flask import *
import uuid_utils.compat as uuid
from werkzeug.utils import secure_filename
import os
import sys
import AzurePlan
import logging
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from azure.monitor.opentelemetry.exporter import AzureMonitorTraceExporter
from opentelemetry.instrumentation.flask import FlaskInstrumentor

# Load environment variables from .env
if os.environ.get("WEBSITE_INSTANCE_ID") is None:
    from dotenv import load_dotenv
    load_dotenv()


# Create a connection string for Application Insights
applicationInsightConnectionString = (
    os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING")
    or os.environ.get("CONNECTIONSTRINGS:APPLICATIONINSIGHTS_CONNECTION_STRING")
)

# Create trace provider and exporter
if applicationInsightConnectionString:
    resource = Resource(attributes={
        "service.name": "flask-telemetry-app"
    })

    provider = TracerProvider(resource=resource)
    trace.set_tracer_provider(provider)

    exporter = AzureMonitorTraceExporter(connection_string=applicationInsightConnectionString)
    span_processor = BatchSpanProcessor(exporter)
    provider.add_span_processor(span_processor)

    logging.info("Application Insights telemetry configured.")

# Flask app setup
app = Flask(__name__, template_folder = os.path.abspath('template'))
FlaskInstrumentor().instrument_app(app)

app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['UPLOAD_FOLDER'] = os.path.abspath('uploads')
app.config['MAX_CONTENT_LENGTH'] = 128 * 1024 * 1024
app.config['version'] = '2.11 (2026-03-01)'
app.config['APP_INSIGHTS_CONNECTION_STRING'] = applicationInsightConnectionString

# Startup logging
tracer = trace.get_tracer(__name__)



ALLOWED_EXTENSIONS = {'csv', 'xls', 'xlsx', 'txt'}
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Default webpage - form
@app.route('/', methods=['GET'])
def index():
    logging.info("Index page accessed")
    return render_template('index.html')


# Import and report
@app.route('/import', methods=['POST'])
def upload_file():
    with tracer.start_as_current_span("upload handler") as span:
        if request.method != 'POST':
            logmsg = "Bad request - POST only"
            logging.info(logmsg)
            span.set_attribute("http.error", logmsg)
            print("ERROR: "+logmsg)
            return redirect('/')
        
        if 'file' not in request.files:
            logmsg = "No file in request"
            logging.info(logmsg)
            span.set_attribute("http.error", logmsg)
            print("ERROR: "+logmsg)
            return redirect('/')

        filedata = request.files['file']
        filename = filedata.filename
        span.set_attribute("filename", filename)

        with tracer.start_as_current_span("AzurePlan.Import") as import_span:
            report = AzurePlan.Import( filename, filedata )
            logmsg = "Report Success"
            logging.info(logmsg)
            import_span.set_attribute(logmsg, bool(report))

        if report:
            with tracer.start_as_current_span("AzurePlan.Calculate") as calc_span:
                billing = AzurePlan.Calculate(report)
                calc_span.set_attribute("billing.size", len(billing) if hasattr(billing, '__len__') else -1)

            return render_template('report.html', report=billing)
        else:
            span.set_attribute("import.failed", True)
            print("wrong filename")
            return redirect('/')


@app.route('/pws/update', methods=['POST', 'GET'])
def update_pws():
    logging.info("Update PWS endpoint accessed")
    print ('content-type:')
    print (request.headers.get('Content-Type'))
    print ('form:')
    print (request.form)
    print ('values:')
    print (request.values)
    print ('data:')
    print (request.data)
    print ('json:')
    data = request.json
    print( data )

    return render_template('index.html')
    

if __name__ == '__main__':
    app.secret_key = 'super secret key'
    app.config['SESSION_TYPE'] = 'filesystem'
    app.debug = False
    app.run()
