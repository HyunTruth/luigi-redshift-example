import logging
from datetime import datetime, date, timedelta, time
import pandas as pd
import requests
import os

# import luigi modules for redshift / s3
import luigi
from luigi.contrib import redshift, s3


# in case the intended folder such as 'tmp' does not exist, create one
def check_and_mkdir(path):
    if os.path.exists(path) is False:
        os.mkdir(path)
    return

#set up logging, using logger data
logger = logging.getLogger('luigi-interface')

# meta data
__author__ = 'Hyun Jin Lee'

DATE_FORMAT = '%Y-%m-%d'
DATEHOUR_FORMAT = '%Y-%m-%dT%H'
DATEMINUTE_FORMAT = '%Y-%m-%dT%H%M'


class path(luigi.Config):
    tmp_path = luigi.Parameter()
    tos3_path = luigi.Parameter()
    s3_load_bucket = luigi.Parameter()


class redshift_auth(luigi.Config):
    """Loads sensitive infos via Luigi's config system to get config variables from the <class_name> tag from luigi.cfg."""
    host = luigi.Parameter(default='')
    database = luigi.Parameter(default='')
    user = luigi.Parameter(default='')
    password = luigi.Parameter(default='')


class s3_auth(luigi.Config):
    """Loads sensitive infos via Luigi's config system to get config variables from the <class_name> tag from luigi.cfg."""
    aws_access_key_id = luigi.Parameter(default='')
    aws_secret_access_key = luigi.Parameter(default='')
    region = luigi.Parameter(default='')
    
class ExampleTask(luigi.WrapperTask):
    start_date = luigi.DateParameter() 
    end_date = luigi.DateParameter()
    def requires(self):
        """
        Anything returned or yielded by requires must have a 'true' complete() method (aka successful output) before 
        this class's run method will execute.
        """
        yield ExampleToRedshift(
            start_date=self.start_date,
            end_date=self.end_date,
            table='annotation_history',
            fn='annotation_history'
        )


class ExampleToRedshift(redshift.S3CopyToTable):
    """A child of redshift.S3CopyToTable class, with overrides such as copy_options"""
    start_date = luigi.DateParameter()
    end_date = luigi.DateParameter()
    fn = luigi.Parameter()
    table_type = luigi.Parameter(default='temp')
    table = luigi.Parameter()
    queries = luigi.ListParameter(default=[])

    copy_options = "CSV BLANKSASNULL EMPTYASNULL TIMEFORMAT 'auto' DATEFORMAT 'auto'"

    # Call all authentication infos
    host = redshift_auth().host
    database = redshift_auth().database
    user = redshift_auth().user
    password = redshift_auth().password
    aws_access_key_id = s3_auth().aws_access_key_id
    aws_secret_access_key = s3_auth().aws_secret_access_key
    

    def s3_load_path(self):
        return self.input()[0].path

    def requires(self):
        return [
            ExampleToS3(start_date=self.start_date, end_date=self.end_date, fn=self.fn)
        ]


class ExampleToS3(luigi.Task):
    """Uses luigi.s3 to send an input file to designated s3_load_bucket."""
    start_date = luigi.DateParameter()
    end_date = luigi.DateParameter()
    fn = luigi.Parameter()
    
    client = s3.S3Client(aws_access_key_id = s3_auth().aws_access_key_id, aws_secret_access_key = s3_auth().aws_secret_access_key, host = s3_auth().region)  
    
    @property
    def fn_src(self):
        return '/'.join(self.input()[0].path.split('/')[-2:])

    def requires(self):
        return [
                LoadingTask(start_date=self.start_date, end_date=self.end_date, fn=self.fn)
        ]


    def output(self):
        return s3.S3Target("{}/{}".format(path().s3_load_bucket, self.fn_src), client=self.client)

    def run(self):
        print('sending to s3 @ {}/{}'.format(path().s3_load_bucket, self.fn_src))
        logger.info('Uploading {} to {}'.format(self.input()[0].path, self.output().path))
        self.client.put(self.input()[0].path, self.output().path)

class LoadingTask(luigi.Task):
    """The main task to be performed, without any dependency. If there are dependencies, then requires() method might be added, as well"""
    start_date = luigi.DateParameter()
    end_date = luigi.DateParameter()
    fn = luigi.Parameter()

    def fn_src(self):
        return '/'.join(self.input()[0].path.split('/')[-1])

    def output(self):
        check_and_mkdir("{path}/{fn}".format(
                path=path().tos3_path, 
                fn=self.fn))
        return luigi.LocalTarget(
            "{path}/{fn}/{start_date}_{end_date}.csv".format(
                path=path().tos3_path, 
                fn=self.fn,
                start_date=self.start_date.strftime(DATE_FORMAT),
                end_date=self.end_date.strftime(DATE_FORMAT)
            )
        )

    def run(self):      
        # load the data in various ways- from sql, read csv, etc and load to pandas.
        # For time-sensitive filtering, the start_date and the end_date parameters may be called using `self.start_date` / `self.end_date`
        # For this example, I'll just create a data with two columns - 'input' and 'output'.
        example = pd.DataFrame([{'input': 'hello', 'output': 'world'}, {'input': 'sql', 'output': 'redshift'}])
        example.to_csv(self.output().path, encoding='utf-8')
        print('serialized locally @ {path}/{fn}/{start_date}_{end_date}.csv'.format(
                path=path().tos3_path, 
                fn=self.fn,
                start_date=self.start_date.strftime(DATE_FORMAT),
                end_date=self.end_date.strftime(DATE_FORMAT)
            ))
        logger.info('serialized locally @ {path}/{fn}/{start_date}_{end_date}.csv'.format(
                path=path().tos3_path, 
                fn=self.fn,
                start_date=self.start_date.strftime(DATE_FORMAT),
                end_date=self.end_date.strftime(DATE_FORMAT)
            ))
        
        
if __name__ == "__main__":
    luigi.run()  # from cli, use `python example_etl.py ExampleTask`
    # if using external parameters, use the form of `python example_etl.py ExampleTask --start-date XXXX-XX-XX --end-date YYYY-YY-YY`
    # For time-scheduling, use cronjobs & scripts
    # add `--local-scheduler` to command if you want to run in a dev mode
    # if using centralized scheduler, luigid daemon process must be running on the background
