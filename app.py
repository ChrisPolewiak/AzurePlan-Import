# Import, extract and calculate billing in AzurePlan subscriptions from Excel and CSV files
# 
# Written By: Chris Polewiak
# Website:	https://github.com/ChrisPolewiak/azure-toolkit/tree/master/AzurePlan-Import

from flask import *
import uuid_utils.compat as uuid
from werkzeug.utils import secure_filename
import os
import AzurePlan
from opencensus.ext.azure.trace_exporter import AzureExporter
from opencensus.ext.flask.flask_middleware import FlaskMiddleware
from opencensus.trace.samplers import ProbabilitySampler

app = Flask(__name__, template_folder = os.path.abspath('template'))
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['UPLOAD_FOLDER'] = os.path.abspath('uploads')
app.config['SECRET_KEY'] = 'yt83t0ghasyg0j'
app.config['MAX_CONTENT_LENGTH'] = 128 * 1024 * 1024
app.config['version'] = '2.05 (2024-07-10)'

# Application Insight For website monitoring
if "CONNECTIONSTRINGS:APPLICATIONINSIGHTS_CONNECTION_STRING" in os.environ:
    AzureAppInsights_ConnectionString = os.environ["CONNECTIONSTRINGS:APPLICATIONINSIGHTS_CONNECTION_STRING"]
    if AzureAppInsights_ConnectionString:
        middleware = FlaskMiddleware(
            app,
            exporter=AzureExporter( connection_string=AzureAppInsights_ConnectionString ),
            sampler=ProbabilitySampler(rate=1.0),
        )


ALLOWED_EXTENSIONS = {'csv', 'xls', 'xlsx', 'txt'}
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Default webpage - form
@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')


# Import and report
@app.route('/import', methods=['POST'])
def upload_file():
    if request.method == 'POST':
        if request.files:
            print (2)
            filedata = request.files['file']
            filename = filedata.filename
            report = AzurePlan.Import( filename, filedata )
            if report:
                billing = AzurePlan.Calculate(report)
                return render_template('report.html', report=billing)
            else:
                print("wrong filename")
        else:
            print("no files")
    else:
        print("not post")
    return redirect('/')


if __name__ == '__main__':
    app.secret_key = 'super secret key'
    app.config['SESSION_TYPE'] = 'filesystem'
    app.debug = False
    app.run()
