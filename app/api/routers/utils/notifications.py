from pprint import pprint
from app.db.settings.crud import retrieve_settings
import smtplib, ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from jinja2 import Environment, FileSystemLoader, select_autoescape
import logging
import requests

logger = logging.getLogger(__name__)

def send_notifications(template_name: str, subject: str, **kwargs) -> None:
    """Send notifications based on pre-defined templates

    Args:
        template (str): name of the template file in email_template
        subject (str): Subject of the email
        kwargs (dict): The values that will be rendered by the Jinja must be sent in here
    """
    guess_who_settings_obj = retrieve_settings()

    #create Jinja environment
    env = Environment(
        loader=FileSystemLoader('/app/app/email_template/'),
        autoescape=select_autoescape(['html', 'xml'])
    )

    #get template
    template = env.get_template(template_name)

    message = template.render(**kwargs)
    
    #Send message to teams if it is set on settings
    if guess_who_settings_obj.teams_url:

        #Green hex
        color = "34eb52"
        if template_name == 'arrival_no_match.html':
            #Red hex
            color = "eb4034"

        send_teams_message(guess_who_settings_obj.teams_url, message, subject, color)

    #Send email if it is set on settings
    if guess_who_settings_obj.email_internal_arrival:
        receivers = get_email_receivers(guess_who_settings_obj.email_internal_arrival)
        for receiver in receivers:
            send_email(
                sender=guess_who_settings_obj.email_sender,
                receiver=receiver,
                subject=subject, 
                message=message,
                smtp_port=guess_who_settings_obj.email_port,
                email_password=guess_who_settings_obj.email_sender_password,
                smtp_server=guess_who_settings_obj.smtp_server,
            )

def get_email_receivers(receivers_string: str) -> list:
    """Function that breaks string into list

    Args:
        receivers_string (str): _description_

    Returns:
        list: List of receivers
    """
    receivers = []
    if ',' in receivers_string:
        receivers = receivers_string.split(',')
    else:
        receivers.append(receivers_string)

    return receivers

def send_teams_message(webhook_url:str, content:str, title:str, color:str="000000") -> dict:
    """Send a teams notification to the desired webhook_url

    Args:
        webhook_url (str): The url you got from the teams webhook configuration
        content (str): Your formatted notification content
        title (str): The message that'll be displayed as title, and on phone notifications
        color (str, optional): Hexadecimal code of the notification's top line color, default corresponds to black. Defaults to "000000".

    Returns:
        int: Status of the request
    """
    response = {"success": True, "message": ''} 
    try:
        response = requests.post(
            url=webhook_url,
            headers={"Content-Type": "application/json"},
            json={
                "themeColor": color,
                "summary": title,
                "sections": [{
                    "activityTitle": title,
                    "activitySubtitle": content
                }],
            },
        )

        if response.status_code != 200:
            raise response.raise_for_status
    except BaseException as error:
        logger.error("Error when trying to send teams message. Reason: %s" % (error))
        response = {"success": False, "message": error} 

    return response.status_code # Should be 200


def send_email(sender: str, receiver: str, subject: str, message: str, smtp_port: str, email_password: str, smtp_server: str) -> dict:
    """Function that generates the email object that helps with sending HTML content

    Args:
        sender (str): Email of the sender
        receiver (str): Email of the receiver
        subject (str): Subject of the email
        message (str): Email body

    Returns:
        dict: {"success": boolean, "message": string}
    """

    email = MIMEMultipart("alternative")
    email["Subject"] = subject
    email["From"] = sender
    email["To"] = receiver
    part2 = MIMEText(message, "html")

    # Add HTML/plain-text parts to MIMEMultipart message
    # The email client will try to render the last part first
    email.attach(part2)

    response = {"success": True, "message": ''}
    try:
        #identify if email should be sent via TLS or SSL
        if int(smtp_port) == 465:
            #create SSL context before sending the email
            with smtplib.SMTP_SSL(smtp_server, smtp_port, context=ssl.create_default_context()) as server:
                #Uncomment the next line for a more verbose debugging
                #server.set_debuglevel(1)
                server.login(sender, email_password)
                server.sendmail(sender, receiver, email.as_string())
        else:
            with smtplib.SMTP(smtp_server, smtp_port) as server:
                server.starttls()

                #if the email server requires authentication
                if email_password:
                    server.login(sender, email_password)
                    server.sendmail(sender, receiver, email.as_string())
                else:
                    server.ehlo(smtp_server)
                    server.mail(sender)
                    server.rcpt(receiver)
                    server.data(email.as_string())
                    server.quit()

    except BaseException as error:
        logger.error("Error when trying to send email to %s. Reason: %s" % (receiver, error))
        response = {"success": False, "message": error} 

    return response
    