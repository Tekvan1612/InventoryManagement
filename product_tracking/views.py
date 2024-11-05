import json
import logging
import os
import traceback
from datetime import datetime
from datetime import timedelta, timezone
from django.utils import timezone
import cloudinary
import cloudinary.api
import cloudinary.uploader
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.core.paginator import Paginator
from django.db import connection, transaction
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.urls import reverse
from django.utils.timezone import now
from django.views.decorators.csrf import csrf_exempt
from psycopg2 import IntegrityError

logger = logging.getLogger(__name__)


# Create your views here.
def index(request):
    # Retrieve session data
    username = request.session.get('username', 'N/A')
    user_id = request.session.get('user_id', None)  # Retrieve the user_id to check if it's correctly stored
    modules = request.session.get('modules', None)

    # Log the retrieved session data
    print(f"Accessing index view")
    print(f"Session Data - Username: {username}, User ID: {user_id}, Modules:{modules}")

    if not username or username == 'N/A':
        print("No username in session; redirecting to login")
        return redirect('login_view')

    # If session data is valid, render the index page with the session data
    return render(request, 'product_tracking/index.html', {
        'username': username,
        'user_id': user_id  # Optionally pass user_id to the template if needed
    })


def custom_login(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        with connection.cursor() as cursor:
            cursor.execute("SELECT user_exists, user_id FROM public.validate_user(%s, %s, %s)",
                           [username, password, True])
            result = cursor.fetchone()

            if result and result[0]:
                user_id = result[1]
                cursor.execute(
                    "SELECT mm.module_name FROM user_junction_module ujm JOIN module_master mm ON ujm.module_id = mm.module_id WHERE ujm.user_id = %s",
                    [user_id])
                modules = cursor.fetchall()

                # Store user info and modules in session
                request.session['username'] = username
                request.session['user_id'] = user_id
                request.session['modules'] = [module[0] for module in modules]

                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'status': 'success', 'redirect_url': reverse('index')})
                else:
                    return redirect(reverse('index'))
            else:
                messages.error(request, "Invalid login details")
                return render(request, 'product_tracking/page-login.html')

    return render(request, 'product_tracking/page-login.html')


def logout_view(request):
    logout(request)
    return redirect('login')


def footer(request):
    return render(request, 'product_tracking/footer.html')


def head(request):
    return render(request, 'product_tracking/head.html')


def header(request):
    return render(request, 'product_tracking/header.html')


def navheader_view(request):
    return render(request, 'product_tracking/navheader.html')


def sidebar(request):
    username = None
    if request.user.is_authenticated:
        username = request.user.username
    return render(request, 'product_tracking/sidebar.html', {'username': username})


def app_calender(request):
    username = request.session.get('username')
    return render(request, 'product_tracking/app-calender.html', {'username': username})


def contact(request):
    username = request.session.get('username')
    return render(request, 'product_tracking/contacts.html', {'username': username})


def employee(request):
    username = None
    if request.user.is_authenticated:
        username = request.user.username
    return render(request, 'product_tracking/employee.html', {'username': username})


def performance(request):
    username = request.session.get('username')
    return render(request, 'product_tracking/performance.html', {'username': username})


def task(request):
    username = request.session.get('username')
    return render(request, 'product_tracking/jobs.html', {'username': username})

# Master Category Module
def add_category(request):
    username = request.session.get('username')
    if request.method == 'POST':
        category_name = request.POST.get('category_name').upper()
        description = request.POST.get('description')  # Fixed typo
        status = request.POST.get('status') == '1'
        created_by = request.session.get('user_id')
        created_date = datetime.now()

        try:
            with connection.cursor() as cursor:
                # Check if the category already exists
                cursor.execute("SELECT COUNT(*) FROM master_category WHERE category_name = %s", [category_name])
                category_count = cursor.fetchone()[0]

                if category_count > 0:
                    return JsonResponse({'success': False, 'message': 'Category Already Exists!'})

                # Insert the new category using the function
                cursor.execute(
                    "SELECT add_category(%s, %s, %s, %s, %s);",
                    [category_name, description, status, created_by, created_date]
                )

            return JsonResponse({'success': True, 'message': 'Category added successfully!'})

        except Exception as e:
            print("An unexpected error occurred:", e)
            return JsonResponse({'success': False, 'message': 'An unexpected error occurred: {}'.format(str(e))})

    else:
        return render(request, 'product_tracking/performance1.html', {'username': username})



def category_list(request):
    try:
        # Create a cursor object using Django's database connection
        with connection.cursor() as cursor:
            # Execute the SQL query to fetch all categories with usernames
            cursor.execute("""
                SELECT
                    mc.category_id,
                    mc.category_name,
                    um.user_name AS created_by,
                    mc.created_date,
                    mc.status
                FROM
                    public.master_category mc
                JOIN
                    public.user_master um
                ON
                    mc.created_by = um.user_id
                ORDER BY
                    mc.category_name
            """)

            # Fetch all rows from the executed query
            rows = cursor.fetchall()

            # Prepare the response data
            categories = [
                {
                    'id': row[0],
                    'category_name': row[1],
                    'created_by': row[2],  # Updated to user_name
                    'created_date': row[3].strftime('%d-%m-%Y') if row[3] else None,
                    'status': row[4]
                }
                for row in rows
            ]

            # Return a JSON response with the categories data
            return JsonResponse({'categories': categories})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
def update_category(request, category_id):
    if request.method == 'POST':
        print('Received POST request to update category details')

        # Extract the form data
        category_name = request.POST.get('categoryName').upper()
        category_description = request.POST.get('categoryDescription', '')
        status = request.POST.get('statusText') == 'true' or request.POST.get(
            'statusText') == 'True' or request.POST.get('statusText') == '1'

        print('Received data:', {
            'category_id': category_id,
            'category_name': category_name,
            'category_description': category_description,
            'status': status,
        })

        try:
            with connection.cursor() as cursor:
                cursor.callproc('update_category', [category_id, category_name, category_description, status])
                updated_category_id = cursor.fetchone()[0]
                print(updated_category_id)
            return JsonResponse(
                {'success': True, 'message': 'Category details updated successfully',
                 'updated_category_id': updated_category_id})
        except Exception as e:
            return JsonResponse({'success': False, 'message': 'Failed to update category details', 'exception': str(e)})
    else:
        return JsonResponse({'success': False, 'message': 'Invalid request method'})


def category_dropdown(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT category_id, category_name FROM get_category_details()')
            categories = [{'id': row[0], 'name': row[1]} for row in cursor.fetchall()]
            print('Categories fetched successfully:', categories)
            return JsonResponse({'categories': categories}, safe=False)
    except Exception as e:
        # Handle exceptions, maybe log the error for debugging
        print("Error fetching categories:", e)
        return JsonResponse({'categories': []})


def get_category_dropdown(request, category_id):
    with connection.cursor() as cursor:
        cursor.execute("SELECT category_id, category_name FROM master_category WHERE category_id = %s", [category_id])
        category_data = cursor.fetchone()
        category_id = category_data[0]
        category_name = category_data[1]

    return JsonResponse({'category_id': category_id, 'category_name': category_name})


# Sub Category Module
def subcategory_list(request, category_id):
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM get_sub(%s)", [category_id])
        rows = cursor.fetchall()

    subcategory_listing = []
    for row in rows:
        created_date = row[6].strftime('%d-%m-%Y')
        subcategory_listing.append({
            'id': row[0],
            'category_name': row[1],
            'name': row[2],
            'type': row[3],
            'status': row[4],
            'created_by': row[5],
            'created_date': created_date
        })

    context = {
        'subcategories': json.dumps(subcategory_listing),
        'category_id': category_id
    }
    return render(request, 'product_tracking/sub-performance1.html', context)


def update_subcategory(request, id):
    if request.method == 'POST':
        print('Received POST request to update sub category details')

        # Extract the form data
        name = request.POST.get('categoryName').upper()

        print('Received data:', {
            'id': id,
            'name': name,

        })

        try:
            with connection.cursor() as cursor:
                cursor.callproc('update_subcategory', [id, name])
                updated_category_id = cursor.fetchone()[0]
                print(updated_category_id)
            return JsonResponse(
                {'message': 'Sub Category details updated successfully', 'updated_category_id': updated_category_id})
        except Exception as e:
            return JsonResponse({'error': 'Failed to update sub category details', 'exception': str(e)})
    else:
        return JsonResponse({'error': 'Invalid request method'})


def add_user(request):
    username = request.session.get('username')
    if request.method == 'POST':
        # Initialize variables from POST data
        username = request.POST.get('username')
        emp_id = request.POST.get('emp_id')
        password = request.POST.get('password')
        status = request.POST.get('status') == '1'
        modules = request.POST.getlist('modules')
        created_by = int(request.session.get('user_id'))
        created_date = datetime.now()

        if not username:
            return JsonResponse({'success': False, 'message': "Error: Username is required."})

        try:
            with transaction.atomic():  # Ensures atomicity
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT add_user(%s, %s, %s, %s, %s, %s, %s);",
                        [username, password, status, modules, created_by, created_date, emp_id]
                    )
                    user_id = cursor.fetchone()[0]

                    if user_id == -1:
                        return JsonResponse(
                            {'success': False, 'message': "Error: An issue occurred while adding the user."})
                    elif user_id:
                        return JsonResponse(
                            {'success': True, 'message': f"User {username} added successfully with ID: {user_id}"})
                    else:
                        return JsonResponse({'success': False, 'message': "Error: User ID is undefined."})
        except Exception as e:
            return JsonResponse({'success': False, 'message': f"Error occurred: {e}"})

    else:
        # Handle GET request: Fetch employee names from the employee table
        with connection.cursor() as cursor:
            cursor.execute("SELECT id, name FROM employee")
            employees = cursor.fetchall()

        employee_data = [{'id': employee[0], 'name': employee[1]} for employee in employees]
        return render(request, 'product_tracking/user.html', {'employee_data': employee_data, 'username': username})

def user_list(request):
    user_listing = []
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM getuser()")
            rows = cursor.fetchall()

            for row in rows:
                created_date_time = row[6].strftime('%d-%m-%Y')
                user_listing.append({
                    'user_id': row[0],
                    'user_name': row[1],
                    'password': row[2],
                    'status': row[3],
                    'modules': row[4] if row[4] else [],  # Ensure modules is a list
                    'created_by': row[5],
                    'created_date_time': created_date_time
                })
    except Exception as e:
        print("Error fetching user list:", e)

    # Implement pagination
    page = request.GET.get('page', 1)
    page_size = request.GET.get('page_size', 10)
    paginator = Paginator(user_listing, page_size)
    page_obj = paginator.get_page(page)

    response = {
        'data': list(page_obj.object_list),
        'total_items': paginator.count,
        'total_pages': paginator.num_pages,
        'current_page': page_obj.number,
    }

    return JsonResponse(response)


def update_user(request, user_id):  # noqa
    if request.method == 'POST':
        user_id = request.POST.get('userId')
        user_name = request.POST.get('username')
        password = request.POST.get('password')
        status = request.POST.get('statusText')
        modules = request.POST.getlist('modules[]')
        emp_id = request.POST.get('emp_id')  # Capture emp_id from the form

        print('Received data:', user_id, user_name, password, status, modules, emp_id)

        try:
            with connection.cursor() as cursor:
                cursor.callproc('update_user', [user_id, user_name, password, status, modules, emp_id])
                cursor.execute("COMMIT;")
            return JsonResponse({'message': 'User details updated successfully', 'user_id': user_id})
        except Exception as e:
            return JsonResponse({'error': str(e)})
    else:
        return JsonResponse({'error': 'Invalid request method'})


def delete_user(request, id):
    if request.method == 'POST':
        try:
            with connection.cursor() as cursor:
                cursor.callproc('deleteuser', [id])
            return JsonResponse({'message': 'User deleted successfully', 'User_id:': id})
        except Exception as e:
            return JsonResponse({'error': 'Failed to delete User', 'exception': str(e)})
    else:
        return JsonResponse({'error': 'Invalid request method'}, status=405)


# Employees Module
def add_employee(request):
    username = request.session.get('username')
    if request.method == 'POST':
        try:
            # Log data for debugging
            print("Received POST data:", request.POST)
            print("Received FILES data:", request.FILES)

            # Validate and extract data
            employee_id = int(request.POST.get('employee_id').strip())
            name = request.POST.get('name')
            email = request.POST.get('email')
            designation = request.POST.get('designation')
            mobile_no = int(request.POST.get('mobile_no').strip())
            gender = request.POST.get('gender')
            joining_date = datetime.strptime(request.POST.get('joining_date'), '%Y-%m-%d').date()
            dob = datetime.strptime(request.POST.get('dob'), '%Y-%m-%d').date()
            reporting_id = request.POST.get('reporting')
            p_address = request.POST.get('p_address')
            c_address = request.POST.get('c_address')
            country = request.POST.get('country')
            state = request.POST.get('state')
            status = request.POST.get('status').lower() == 'true'
            blood_group = request.POST.get('bloodGroup')
            created_by = request.session.get('user_id')
            created_date = datetime.now().replace(tzinfo=None)  # timestamp without timezone
            profile_photo = request.FILES.get('profile_photo')
            attachment_images = request.FILES.getlist('attachments[]')

            # Cloudinary upload for profile photo
            profile_photo_url = None
            if profile_photo:
                if profile_photo.size < 4000 or profile_photo.size > 12288:
                    return JsonResponse({'error': 'Profile photo size must be between 5KB and 12KB.'}, status=400)
                upload_result = cloudinary.uploader.upload(profile_photo, folder="profilepic/")
                profile_photo_url = upload_result['secure_url']  # Get the URL of the uploaded image

            # Cloudinary upload for attachments
            image_urls = []
            for image in attachment_images[:2]:  # Limiting to first 2 attachments
                if image:
                    upload_result = cloudinary.uploader.upload(image, folder="uploads/")
                    image_urls.append(upload_result['secure_url'])  # Get the URL of the uploaded image

            # Ensure there are at least two entries in image_urls to avoid index errors
            while len(image_urls) < 2:
                image_urls.append(None)

            # Check for duplicates
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT COUNT(*) FROM employee
                    WHERE employee_id = %s OR email = %s OR mobile_no = %s
                """, [employee_id, email, mobile_no])
                duplicate_count = cursor.fetchone()[0]

            if duplicate_count > 0:
                return JsonResponse({'error': 'Employee with this ID, email, or mobile number already exists.'},
                                    status=400)

            # Fetch reporting name
            with connection.cursor() as cursor:
                cursor.execute("SELECT name FROM employee WHERE id = %s", [reporting_id])
                reporting_name = cursor.fetchone()
                if reporting_name is None:
                    return JsonResponse({'error': 'Invalid reporting ID.'}, status=400)
                reporting_name = reporting_name[0]

            # Call stored procedure
            try:
                with connection.cursor() as cursor:
                    cursor.callproc('add_employee', [
                        employee_id, name, email, designation, mobile_no, gender,
                        joining_date, dob, reporting_name, p_address, c_address, country, state,
                        status, blood_group, created_by, created_date,
                        profile_photo_url, image_urls[0], image_urls[1]
                    ])
            except IntegrityError as e:
                return JsonResponse({'error': 'Integrity error occurred: ' + str(e)}, status=400)

            return JsonResponse({'success': 'Employee added successfully'}, status=200)

        except Exception as e:
            print(f"An unexpected error occurred: {str(e)}")
            return JsonResponse({'error': 'An unexpected error occurred: ' + str(e)}, status=500)

    return render(request, 'product_tracking/employee.html', {'employees': get_all_employees(), 'username': username})


def get_all_employees():
    with connection.cursor() as cursor:
        cursor.execute("SELECT id, name FROM employee")
        employees = [{'id': row[0], 'name': row[1]} for row in cursor.fetchall()]
    return employees


def employee_dropdown(request):
    search_query = request.GET.get('query', '')  # Capture search query from frontend
    with connection.cursor() as cursor:
        if search_query:
            cursor.execute("SELECT id, name FROM employee WHERE name ILIKE %s", ['%' + search_query + '%'])
        else:
            cursor.execute("SELECT id, name FROM employee")
        employees = cursor.fetchall()
        employee_list = [{'id': emp[0], 'name': emp[1]} for emp in employees]

    return JsonResponse({'employees': employee_list})


def employee_list(request):
    employee_listing = []
    try:
        with connection.cursor() as cursor:
            # Fetch employee details
            cursor.execute("SELECT * FROM get_employee_details()")
            rows = cursor.fetchall()
            # print('Check the employee Details:', rows)

            for index, row in enumerate(rows):
                # print('Check the for loop')
                # Log row structure for debugging
                logger.debug(f"Row data: {row}")

                # Extract each field from the row
                employee_id = row[1]
                name = row[2]
                email = row[3]
                designation = row[4]
                mobile_no = row[5]
                gender = row[6]
                joining_date = row[7].strftime('%Y-%m-%d') if row[7] else None
                dob = row[8].strftime('%Y-%m-%d') if row[8] else None
                reporting_name = row[9]
                p_address = row[10]
                c_address = row[11]
                country = row[12]
                state = row[13]
                status = row[14]
                blood_group = row[15]
                created_by = row[16]  # Assuming this is created_by, adjust as necessary
                created_date = row[17].strftime('%Y-%m-%d') if row[17] else None  # Format created_date
                profile_pic = row[18]  # Profile picture path
                attachments = row[19] or []  # Attachments array
                # print('Fetch the Form DATA:', employee_id,name,email, designation,mobile_no, gender, joining_date, dob, reporting_name, p_address, c_address, country,
                # profile_pic, attachments)

                # Handle profile picture URL
                if profile_pic:
                    # If the profile_pic already contains a full URL (e.g., Cloudinary URL)
                    if profile_pic.startswith('http://') or profile_pic.startswith('https://'):
                        image_url = profile_pic  # Use the URL as is
                    else:
                        # Otherwise, assume it's a local file path and construct the media URL
                        image_url = f'{settings.MEDIA_URL}{profile_pic}'.replace('\\', '/')
                else:
                    # Fallback to default profile picture if none is provided
                    image_url = f'{settings.MEDIA_URL}profilepic/default.jpg'

                # Handle attachments (array of images)
                attachment_urls = []
                for attachment in attachments:
                    if attachment:
                        attachment_url = os.path.join(settings.MEDIA_URL, attachment).replace('\\', '/')
                        attachment_urls.append(attachment_url)

                # Add employee details to the list
                employee_listing.append({
                    'sr_no': index + 1,
                    'id': row[0],
                    'employee_id': employee_id,
                    'name': name,
                    'email': email,
                    'mobile_no': mobile_no,
                    'designation': designation,
                    'gender': gender,
                    'joining_date': joining_date,
                    'dob': dob,
                    'reporting': reporting_name,
                    'p_address': p_address,
                    'c_address': c_address,
                    'country': country,
                    'state': state,
                    'status': status,
                    'blood_group': blood_group,
                    'created_by': created_by,
                    'created_date': created_date,
                    'profile_pic': image_url,
                    'attachments': attachment_urls  # List of attachment URLs
                })
            # print('Check the Employee Listing:', employee_listing)

    except Exception as e:
        logger.error("An error occurred while fetching the employee list: %s", str(e), exc_info=True)
        return JsonResponse({'error': 'An error occurred while fetching the employee list: ' + str(e)}, status=500)

    # Pagination
    page = int(request.GET.get('page', 1))
    page_size = int(request.GET.get('page_size', 10))
    paginator = Paginator(employee_listing, page_size)
    page_obj = paginator.get_page(page)

    response = {
        'data': list(page_obj.object_list),
        'total_items': paginator.count,
        'total_pages': paginator.num_pages,
        'current_page': page_obj.number,
    }

    return JsonResponse(response)


@csrf_exempt
def delete_attachment(request):
    if request.method == 'POST':
        attachment_id = request.POST.get('attachment_id')

        if attachment_id:
            try:
                with connection.cursor() as cursor:
                    cursor.execute("DELETE FROM employee_images WHERE id = %s", [attachment_id])
                return JsonResponse({'success': 'Attachment deleted successfully'})
            except Exception as e:
                return JsonResponse({'error': 'Error deleting attachment: ' + str(e)}, status=400)
        else:
            return JsonResponse({'error': 'Invalid attachment ID'}, status=400)
    return JsonResponse({'error': 'Invalid request'}, status=400)


def modify_employee(request):
    if request.method == 'POST':
        operation = request.POST.get('operation')
        emp_id = request.POST.get('id')

        if not emp_id or not emp_id.isdigit():
            return JsonResponse({'error': 'Invalid employee ID'}, status=400)

        emp_id = int(emp_id)

        if operation == 'update':
            # Extract employee details from the POST request
            emp_employee_id = request.POST.get('employee_id') or None
            emp_name = request.POST.get('name') or None
            emp_email = request.POST.get('email') or None
            emp_designation = request.POST.get('designation') or None
            emp_mobile_no = request.POST.get('mobile_no') or None
            emp_gender = request.POST.get('gender') or None
            emp_joining_date = request.POST.get('joining_date') or None
            emp_dob = request.POST.get('dob') or None
            emp_reporting = request.POST.get('reporting') or None
            emp_p_address = request.POST.get('p_address') or None
            emp_c_address = request.POST.get('c_address') or None
            emp_country = request.POST.get('country') or None
            emp_state = request.POST.get('state') or None
            emp_status = request.POST.get('status') == 'true'
            emp_blood_group = request.POST.get('blood_group') or None
            removed_profile_pic = request.POST.get('removed_profile_pic') == 'true'

            try:
                # Process removed attachments from the request
                removed_attachments = request.POST.get('removed_attachments')
                removed_attachments = json.loads(removed_attachments) if removed_attachments else []

                with transaction.atomic():
                    # Update employee details in the database using a stored procedure or SQL
                    with connection.cursor() as cursor:
                        cursor.execute(
                            """
                            SELECT modify_employee(
                                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                            )
                            """,
                            [
                                operation,
                                emp_id,
                                int(emp_employee_id) if emp_employee_id else None,
                                emp_name,
                                emp_email,
                                emp_designation,
                                int(emp_mobile_no) if emp_mobile_no else None,
                                emp_gender,
                                emp_joining_date,
                                emp_dob,
                                emp_reporting,
                                emp_p_address,
                                emp_c_address,
                                emp_country,
                                emp_state,
                                emp_status,
                                emp_blood_group
                            ]
                        )

                    # Handle profile photo upload to Cloudinary or local
                    profile_photo = request.FILES.get('profile_photo')
                    if profile_photo:
                        try:
                            # Upload new profile photo to Cloudinary
                            upload_result = cloudinary.uploader.upload(profile_photo, folder="profilepic/")
                            profile_pic_url = upload_result['secure_url']

                            # Insert or update profile photo URL in the database
                            with connection.cursor() as cursor:
                                cursor.execute(
                                    "SELECT id FROM employee_images WHERE employee_id = %s AND images LIKE %s",
                                    [emp_id, '%profilepic%'])
                                existing_image = cursor.fetchone()

                                if existing_image:
                                    # Update profile photo if it exists
                                    cursor.execute(
                                        "UPDATE employee_images SET images = %s WHERE employee_id = %s AND images LIKE %s",
                                        [profile_pic_url, emp_id, '%profilepic%']
                                    )
                                else:
                                    # Insert new profile photo if it doesn't exist
                                    cursor.execute(
                                        "INSERT INTO employee_images (employee_id, images) VALUES (%s, %s)",
                                        [emp_id, profile_pic_url]
                                    )
                        except Exception as e:
                            return JsonResponse({'error': 'Error uploading profile photo: ' + str(e)}, status=400)

                    # Handle attachment uploads (new attachments)
                    attachments = request.FILES.getlist('attachments')
                    for attachment in attachments:
                        try:
                            upload_result = cloudinary.uploader.upload(attachment, folder="uploads/")
                            attachment_url = upload_result['secure_url']

                            # Insert new attachments in the database
                            with connection.cursor() as cursor:
                                cursor.execute(
                                    "INSERT INTO employee_images (employee_id, images) VALUES (%s, %s)",
                                    [emp_id, attachment_url]
                                )
                        except Exception as e:
                            return JsonResponse({'error': 'Error uploading attachment: ' + str(e)}, status=400)

                    # Remove profile picture if requested
                    if removed_profile_pic:
                        with connection.cursor() as cursor:
                            cursor.execute(
                                "DELETE FROM employee_images WHERE employee_id = %s AND images LIKE %s",
                                [emp_id, '%profilepic%']
                            )

                    # Remove attachments by ID
                    for attachment_id in removed_attachments:
                        with connection.cursor() as cursor:
                            cursor.execute(
                                "DELETE FROM employee_images WHERE id = %s",
                                [attachment_id]
                            )

                return JsonResponse({'success': 'Employee updated successfully'})
            except Exception as e:
                logger.error("Error updating employee: %s", str(e))
                return JsonResponse({'error': str(e)}, status=400)

        elif operation == 'delete':
            try:
                # Delete employee using a stored procedure or SQL
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT delete_employee(%s)",
                        [emp_id]
                    )
                return JsonResponse({'success': 'Employee deleted successfully'})
            except Exception as e:
                logger.error("Error deleting employee: %s", str(e))
                return JsonResponse({'error': str(e)}, status=400)

    return JsonResponse({'error': 'Invalid request'}, status=400)


# Equipment Module
def add_equipment(request):
    if request.method == 'POST':
        equipment_name = request.POST.get('equipment_name').upper()
        subcategory_name = request.POST.get('subcategory_id').upper()
        category_name = request.POST.get('category_name').upper()
        type = request.POST.get('type')
        dimension_h = request.POST.get('dimension_h')
        dimension_w = request.POST.get('dimension_w')
        dimension_l = request.POST.get('dimension_l')
        weight = request.POST.get('weight')
        volume = request.POST.get('volume')
        hsn_no = request.POST.get('hsn_no')
        country_origin = request.POST.get('country_origin')
        attachment = request.FILES.get('attachment')
        status = request.POST.get('status')
        created_by = request.session.get('user_id')
        created_date = datetime.now()

        attachment_path = None
        if attachment:
            attachment_path = os.path.join(settings.MEDIA_ROOT, 'attachments', attachment.name)
            os.makedirs(os.path.dirname(attachment_path), exist_ok=True)
            with open(attachment_path, 'wb') as f:
                for chunk in attachment.chunks():
                    f.write(chunk)

        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT public.add_equipment_list(
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    );
                    """,
                    [
                        equipment_name,
                        subcategory_name,
                        category_name,
                        type,
                        dimension_h,
                        dimension_w,
                        dimension_l,
                        weight,
                        volume,
                        hsn_no,
                        country_origin,
                        attachment_path if attachment else None,
                        status,
                        created_by,
                        created_date
                    ]
                )
                return JsonResponse({'success': True})
        except IntegrityError as e:
            error_message = str(e)
            if 'duplicate key value violates unique constraint "unique_equipment_name"' in error_message:
                error_message = 'Equipment name already exists. Please choose a different name.'
            print("An unexpected error occurred:", error_message)
            return JsonResponse({'success': False, 'message': error_message})
        except Exception as e:
            print("An unexpected error occurred:", e)
            return JsonResponse({'success': False, 'message': 'Equipment Already Exists!'})
    else:
        username = None
        if request.user.is_authenticated:
            username = request.user.username
        subcategories = []
        try:
            with connection.cursor() as cursor:
                cursor.execute('SELECT id, category_name, name FROM get_sub()')
                subcategories = [{'id': row[0], 'category_name': row[1], 'name': row[2]} for row in cursor.fetchall()]
        except Exception as e:
            print("Error fetching subcategories:", e)
        return render(request, 'product_tracking/Equipment.html',
                      {'username': username, 'subcategories': subcategories})


def insert_vendor(request):
    if request.method == 'POST':
        # Retrieve form data
        vendor_name = request.POST.get('vendor_name')
        purchase_date = request.POST.get('purchase_date')
        unit_price = request.POST.get('unit_price')
        rental_price = request.POST.get('rental_price')
        reference_no = request.POST.get('reference_no')
        unit = request.POST.get('unitValue')
        attachment = request.FILES.get('attachment')

        # Extract dynamically generated input box values
        serial_numbers = []
        barcode_numbers = []
        for i in range(1, int(unit) + 1):
            serial_number = request.POST.get(f'serialNumber{i}', '')
            barcode_number = request.POST.get(f'barcodeNumber{i}', '')
            serial_numbers.append(serial_number)
            barcode_numbers.append(barcode_number)

        equipment_id = request.POST.get('equipmentId')
        subcategory_id = None
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT sub_category_id FROM equipment_list WHERE id = %s",
                    [equipment_id]
                )
                subcategory_id = cursor.fetchone()[0]
        except Exception as e:
            print(f"An unexpected error occurred while fetching equipment ID: {e}")

        # Handle file upload
        attachment_path = None
        if attachment:
            attachment_path = os.path.join(settings.MEDIA_ROOT, 'attachments', attachment.name)
            os.makedirs(os.path.dirname(attachment_path), exist_ok=True)  # Ensure the directory exists
            with open(attachment_path, 'wb') as f:
                for chunk in attachment.chunks():
                    f.write(chunk)

        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT add_stock(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULL);",
                    [equipment_id, vendor_name, purchase_date, unit_price, rental_price, reference_no, attachment_path,
                     unit, serial_numbers, barcode_numbers]
                )
            print('Stock Details added successfully')
            return redirect(f'/equipment_list/?subcategory_id={subcategory_id}')
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            return render(request, 'product_tracking/index.html', {'error': 'An unexpected error occurred'})
    else:
        # Handle GET request
        username = None
        if request.user.is_authenticated:
            username = request.user.username
        return render(request, 'product_tracking/performance.html', {'username': username})


def subcategory_dropdown(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT id, category_name, name FROM get_sub()')
            subcategories = [{'id': row[0], 'category_name': row[1], 'name': row[2]} for row in cursor.fetchall()]
            print('sub category fetched successfully:', subcategories)
            return JsonResponse({'subcategories': subcategories}, safe=False)
    except Exception as e:
        # Handle exceptions, maybe log the error for debugging
        print("Error fetching sub category:", e)
        return JsonResponse({'subcategories': []})


def get_category_name(request):
    try:
        subcategory_id = request.GET.get('subcategory_id')
        # Fetch category name based on subcategory_id
        with connection.cursor() as cursor:
            cursor.execute('SELECT category_name FROM get_sub() WHERE id = %s', [subcategory_id])
            row = cursor.fetchone()
            category_name = row[0] if row else None
        return JsonResponse({'category_name': category_name})
    except Exception as e:
        # Handle exceptions, maybe log the error for debugging
        print("Error fetching category name:", e)
        return JsonResponse({'category_name': None})


def subcategory_list(request, category_id):
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM get_subcategory(%s)", [category_id])
        rows = cursor.fetchall()

    subcategory_listing = []
    for row in rows:
        created_date = row[6].strftime('%d-%m-%Y')
        subcategory_listing.append({
            'id': row[0],
            'category_name': row[1],
            'name': row[2],
            'type': row[3],
            'status': row[4],
            'created_by': row[5],
            'created_date': created_date
        })

    context = {
        'subcategories': json.dumps(subcategory_listing),
        'category_id': category_id
    }
    return render(request, 'product_tracking/sub-performance1.html', context)


def equipment_list(request):
    print('fetch the data')
    username = request.session.get('username')
    subcategory_id = request.GET.get('subcategory_id')
    if not subcategory_id:
        return JsonResponse({'error': 'Missing subcategory_id parameter'}, status=400)
    print('Sub category ID:', subcategory_id)

    try:
        subcategory_id = int(subcategory_id)
    except ValueError:
        return JsonResponse({'error': 'Invalid subcategory_id parameter'}, status=400)

    equipment_listing = []
    try:
        print('inside the list of try block')
        with connection.cursor() as cursor:
            print('inside the cursor object')
            cursor.execute("SELECT * FROM get_equipment_list(%s)", [subcategory_id])
            rows = cursor.fetchall()

            print('fetch the data')
            for row in rows:
                print('inside the list of rows')
                created_date = row[15].strftime('%d-%m-%Y')
                equipment_listing.append({
                    'id': row[0],
                    'equipment_name': row[1],
                    'sub_category_name': row[2],
                    'category_type': row[3],
                    'type': row[4],
                    'dimension_height': row[5],
                    'dimension_width': row[6],
                    'dimension_length': row[7],
                    'weight': row[8],
                    'volume': row[9],
                    'hsn_no': row[10],
                    'country_origin': row[11],
                    'attachment': row[12],
                    'status': row[13],
                    'created_by': row[14],
                    'created_date': created_date
                })
                print('fetch the data:', equipment_listing)
    except Exception as e:
        print("Error fetching equipment list:", e)
        return JsonResponse({'error': str(e)}, status=500)

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'equipments': equipment_listing})

    context = {
        'equipment_listing': json.dumps(equipment_listing),
        'subcategory_id': subcategory_id,
        'username': username
    }
    return render(request, 'product_tracking/Equipment.html', context)


def edit_subcategory_dropdown(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT id, category_name, name FROM get_sub()')
            sub = [{'id': row[0], 'category_name': row[1], 'name': row[2]} for row in cursor.fetchall()]
            print('sub category fetched successfully:', sub)
            return JsonResponse({'sub': sub}, safe=False)
    except Exception as e:
        # Handle exceptions, maybe log the error for debugging
        print("Error fetching sub category:", e)
        return JsonResponse({'sub': []})


def edit_get_category_name(request):
    try:
        subcategory_id = request.GET.get('subcategory_id')
        # Fetch category name based on subcategory_id
        with connection.cursor() as cursor:
            cursor.execute('SELECT category_name FROM get_sub() WHERE id = %s', [subcategory_id])
            row = cursor.fetchone()
            category_name = row[0] if row else None
        return JsonResponse({'category_name': category_name})
    except Exception as e:
        # Handle exceptions, maybe log the error for debugging
        print("Error fetching category name:", e)
        return JsonResponse({'category_name': None})


def fetch_stock_status(request, equipment_id):
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM get_stock_status(%s)", [equipment_id])
        stock_data = cursor.fetchone()
        print('Equipment ID:', equipment_id)
        print('Equipment ID:', equipment_id, stock_data)

    if stock_data is not None:
        unit_count = stock_data[0]
        stock_status = 'Stock in completed' if unit_count > 0 else 'Stock in pending'
    else:
        unit_count = 0
        stock_status = 'Stock in pending'
    return JsonResponse({'unit_count': unit_count, 'stock_status': stock_status})


def fetch_serial_barcode_no(request, equipment_id):
    # Execute the PostgreSQL function
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM get_serial_barcode_no(%s)", [equipment_id])
        rows = cursor.fetchall()
        if rows:
            # If multiple rows are returned, create a list of dictionaries
            data = [{'serial_number': row[0], 'barcode_number': row[1]} for row in rows]
        else:
            # If no rows are returned, return an error
            return JsonResponse({'error': 'No data found for equipment ID ' + str(equipment_id)}, status=404)

    return JsonResponse(data, safe=False)


def get_dimension_list(request, equipment_id):
    print('inside the function')
    # Execute the PostgreSQL function
    with connection.cursor() as cursor:
        print('inside the object of cursor')
        cursor.execute("SELECT * FROM get_dimension_list_stock(%s)", [equipment_id])
        rows = cursor.fetchall()  # Fetch all rows
        print('row values:', rows)
        if rows:
            # Initialize dictionaries to hold single and aggregated data
            dimension_details = {}
            stock_details = {
                'vender_name': '',
                'purchase_date': '',
                'unit_price': '',
                'rental_price': '',
                'reference_no': '',
                'unit': '',
                'serial_no': [],
                'barcode_no': []
            }

            # Extract common dimension details from the first row
            first_row = rows[0]
            dimension_details = {
                'dimension_height': first_row[0] or '',
                'dimension_width': first_row[1] or '',
                'dimension_length': first_row[2] or '',
                'weight': first_row[3] or '',
                'volume': first_row[4] or '',
                'hsn_no': first_row[5] or '',
                'country_origin': first_row[6] or '',
                'status': first_row[7] or '',
                'created_by': first_row[8] or '',
                'created_date': first_row[9].strftime('%d-%m-%Y') if first_row[9] else ''
            }

            # Check if any row has serial numbers or barcode numbers
            has_stock_details = any(row[16] or row[17] for row in rows)

            if has_stock_details:
                # Aggregate serial numbers and barcode numbers
                for row in rows:
                    stock_details['serial_no'].append(row[16] or '')
                    stock_details['barcode_no'].append(row[17] or '')

                # Assign single values to stock_details
                stock_details['vender_name'] = first_row[10] or ''
                stock_details['purchase_date'] = first_row[11].strftime('%d-%m-%Y') if first_row[11] else ''
                stock_details['unit_price'] = first_row[12] or ''
                stock_details['rental_price'] = first_row[13] or ''
                stock_details['reference_no'] = first_row[14] or ''
                stock_details['unit'] = first_row[15] or ''

            # Merge dictionaries
            data = {**dimension_details, **stock_details}
            print('Values are shown in the table are:', data)
        else:
            # If no rows are returned, return an error
            return JsonResponse({'error': 'No data found for equipment ID ' + str(equipment_id)}, status=404)

    return JsonResponse(data)


def stock_list(request):
    username = request.session.get('username')
    return render(request, 'product_tracking/Stock_details.html', {'username': username})


def fetch_stock_equipment_list(request):
    if request.method == 'POST':
        category_id = request.POST.get('category_type', '')
        start = int(request.POST.get('start', 0))
        limit = int(request.POST.get('limit', 10))

        print(f"Fetching data for category: {category_id}, start: {start}, limit: {limit}")

        # Fetch paginated data
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT * FROM public.get_list(%s) OFFSET %s LIMIT %s
            """, [category_id, start, limit])
            rows = cursor.fetchall()
            print(f"Fetched rows: {rows}")

        # Fetch total count
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT COUNT(*) FROM (
                    SELECT DISTINCT el.equipment_name, el.sub_category_id, el.category_type
                    FROM public.equipment_list el
                    LEFT JOIN public.sub_category sc ON el.sub_category_id = sc.id
                    LEFT JOIN public.stock_details sd ON el.id = sd.equipment_id
                    WHERE sc.category_id = %s
                ) AS distinct_items
            """, [category_id])
            total_items = cursor.fetchone()[0]
            print(f"Total items: {total_items}")

        equipment_list = []
        for row in rows:
            equipment_list.append({
                'equipment_name': row[0],
                'sub_category_name': row[1],  # Ensure this is the correct index for sub_category_name
                'category_type': row[2],
                'unit_price': row[3],
                'rental_price': row[4],
                'total_units': row[5],
            })

        print(f"Equipment list: {equipment_list}")

        return JsonResponse({'totalItems': total_items, 'data': equipment_list}, safe=False)
    else:
        return JsonResponse({'error': 'Invalid request'})


def stock_in(request, equipment_id):
    print('inside the stock in')
    try:
        print('Execute this try block')
        with connection.cursor() as cursor:
            print('Execute the cursor object')
            cursor.execute("SELECT * FROM public.fetch_stock_details(%s)", [equipment_id])
            rows = cursor.fetchall()
            print('Fetch the stock_details:', rows)

        if rows:
            print('inside the rows')
            data = [{'id': row[0], 'serial_number': row[1], 'barcode_number': row[2], 'vendor_name': row[3],
                     'unit_price': row[4],
                     'rental_price': row[5], 'purchase_date': row[6], 'reference_no': row[7]} for row in rows]
            print('insert the correct data:', data)
        else:
            return JsonResponse({'error': 'No data found for equipment ID ' + str(equipment_id)}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

    # Return the data as a JSON response
    return JsonResponse(data, safe=False)


def update_stock_in(request, row_id):
    if request.method == 'POST':
        try:
            vender_name = request.POST.get('vender_name')
            serial_number = request.POST.get('serial_number')
            barcode_number = request.POST.get('barcode_number')
            unit_price = request.POST.get('unit_price')
            rental_price = request.POST.get('rental_price')
            purchase_date = request.POST.get('purchase_date')
            reference_no = request.POST.get('reference_no')

            with connection.cursor() as cursor:
                cursor.callproc('update_stock_in_function', [
                    row_id,
                    vender_name,
                    serial_number,
                    barcode_number,
                    unit_price,
                    rental_price,
                    purchase_date,
                    reference_no
                ])
            return JsonResponse({'success': True, 'message': 'Updated successfully'})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e), 'message': 'Not Updated successfully'})
    else:
        return JsonResponse({'success': False, 'error': 'Invalid request method.'})


def fetch_stock_details_by_name(request):
    equipment_name = request.GET.get('equipment_name', '')

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT *
            FROM public.fetch_stock_details_by_name(%s)
            """,
            [equipment_name]
        )
        results = cursor.fetchall()

    # Format the results into a JSON response
    response_data = []
    for row in results:
        data = {
            'serial_number': row[0],
            'barcode_number': row[1],
            'vendor_name': row[2],
            'unit_price': row[3],
            'rental_price': row[4],
            'purchase_date': row[5],
            'reference_no': row[6],
        }
        response_data.append(data)

    return JsonResponse(response_data, safe=False)


@csrf_exempt
def add_event_view(request):
    if request.method == 'POST':
        action = request.POST.get('action')
        event_id = request.POST.get('event_id')
        venue = request.POST.get('venue')
        client_name = request.POST.get('client_name')
        person_name = request.POST.get('person_name')
        created_by = request.session.get('user_id')
        start_date = request.POST.get('start_date')
        end_date = request.POST.get('end_date')

        # Ensure event_id is an integer if provided
        event_id = int(event_id) if event_id else None

        # Set created_date for CREATE and UPDATE actions
        created_date = datetime.now() if action in ['CREATE', 'UPDATE'] else None

        # Validation for CREATE and UPDATE actions
        if action == 'CREATE':
            if not (venue and client_name and person_name and start_date and end_date):
                return JsonResponse({'success': False, 'error_message': 'All fields must be filled out'}, status=400)
        elif action == 'UPDATE':
            if not event_id:
                return JsonResponse({'success': False, 'error_message': 'Event ID is required for update'}, status=400)
            if not (venue and client_name and person_name and start_date and end_date):
                return JsonResponse({'success': False, 'error_message': 'All fields must be filled out'}, status=400)
        elif action == 'DELETE':
            if not event_id:
                return JsonResponse({'success': False, 'error_message': 'Event ID is required for deletion'},
                                    status=400)
        else:
            return JsonResponse({'success': False, 'error_message': 'Invalid action'}, status=400)

        with connection.cursor() as cursor:
            cursor.callproc('public.manage_event', [
                action,
                event_id,
                venue,
                client_name,
                person_name,
                created_by,
                created_date,
                start_date,
                end_date
            ])
            result = cursor.fetchall()

        # Process the result to convert it to JSON serializable format
        columns = [col[0] for col in cursor.description]
        result = [dict(zip(columns, row)) for row in result]

        return JsonResponse({'success': True, 'data': result})

    return JsonResponse({'success': False, 'error_message': 'Invalid request method or action'}, status=400)


def get_eventvalue(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM public.calender")
            events = cursor.fetchall()
            events_list = []
            for event in events:
                start_date = event[6].strftime('%Y-%m-%d') if event[6] else None
                end_date = (event[7] + timedelta(days=1)).strftime('%Y-%m-%d') if event[7] else start_date
                events_list.append({
                    'id': event[0],
                    'title': f"{event[1]} - {event[2]} - {event[3]}",
                    'start': start_date,
                    'end': end_date,
                    'extendedProps': {
                        'venue': event[1],
                        'client_name': event[2],
                        'person_name': event[3]
                    }
                })
            return JsonResponse(events_list, safe=False)
    except Exception as e:
        logger.error(f"Error occurred: {e}")
        return JsonResponse({'success': False, 'error_message': 'There was an error retrieving events.'}, status=500)


def add_job(request):
    username = request.session.get('username')
    print('inside the add job function')
    if request.method == 'POST':
        print('inside the add job post method')
        title = request.POST.get('title')
        client_name = request.POST.get('client_name')
        contact_person_name = request.POST.get('contact_person_name')
        contact_person_number = request.POST.get('contact_person_number')
        venue_address = request.POST.get('venue_address')
        status = request.POST.get('status')
        crew_types = request.POST.getlist('crew_type')
        crew_type = ','.join(crew_types)
        no_of_container = request.POST.get('no_of_container')
        employees = request.POST.getlist('prep_sheet')
        employee = ','.join(employees)
        setup_date = request.POST.get('setup_date')
        rehearsal_date = request.POST.get('rehearsal_date')
        start_date = request.POST.get('start_date')
        end_date = request.POST.get('end_date')
        total_days = request.POST.get('total_days')
        amount_row = request.POST.get('amount_row')
        discount = request.POST.get('discount')
        discounted_amount = request.POST.get('discounted_amount')
        total_amount = request.POST.get('total_amount')

        print('fetch the amount after discount:', discounted_amount)

        # Fetching multiple values as lists
        category_name = request.POST.getlist('category_name')
        equipment_ids = request.POST.getlist('equipment_name')
        quantities = request.POST.getlist('quantity')
        number_of_days = request.POST.getlist('number_of_days')
        amounts = request.POST.getlist('amount')
        print('Fetch the category NAME:', category_name)

        # Convert strings to integers for category_ids and equipment_ids
        equipment_ids = [int(id) for id in equipment_ids]

        # Assuming you have the user ID stored in the session for the created_by field
        created_by = request.session.get('user_id')
        created_date = datetime.now()

        print('Fetch the data:', title, client_name, contact_person_name, contact_person_number, venue_address, status,
              crew_type, no_of_container, employee,
              setup_date, rehearsal_date, start_date,
              end_date, total_days, amount_row, discount, discounted_amount, total_amount, category_name, equipment_ids,
              quantities, number_of_days, amounts, created_by, created_date)

        try:
            with connection.cursor() as cursor:
                # Print the query for debugging purposes
                query = f"SELECT * FROM jobs_master_list('CREATE', NULL, NULL, '{title}', '{client_name}', '{venue_address}', '{status}', '{crew_type}', '{no_of_container}', '{employee}', '{setup_date}'::date, '{rehearsal_date}'::date, '{start_date}'::date, '{end_date}'::date, '{discounted_amount}', ARRAY{category_name}::integer[], ARRAY{equipment_ids}::integer[], ARRAY{quantities}::varchar[], ARRAY{number_of_days}::varchar[], ARRAY{amounts}::varchar[], {created_by}, '{created_date}');"
                print("Executing query:", query)

                cursor.callproc(
                    'jobs_master_list',
                    (
                        'CREATE', None, None, title, client_name, contact_person_name, contact_person_number,
                        venue_address,
                        status, crew_type, no_of_container,
                        employee, setup_date, rehearsal_date, start_date, end_date, total_days, amount_row, discount,
                        discounted_amount, total_amount, category_name, equipment_ids,
                        quantities, number_of_days, amounts, created_by, created_date)
                )
                # Fetch the returned data from the cursor
                data = cursor.fetchall()
                print('Returned data:', data)
                return JsonResponse({'success': True, 'data': data})
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            return JsonResponse({'success': False, 'error': str(e)}, status=500)
    return render(request, 'product_tracking/jobs.html', {'username': username})


def fetch_client_name(request):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT DISTINCT type, name, company_name FROM public.connects"
        )
        client_names = []
        for row in cursor.fetchall():
            client_type, name, company_name = row
            if name:
                client_names.append({'type': client_type, 'name': name})
            if company_name:
                client_names.append({'type': client_type, 'name': company_name})

    return JsonResponse({'client_names': client_names})


def fetch_venue_name(request):
    query = request.GET.get('query', '').strip()
    if not query:
        return JsonResponse({'venue_names': []})  # Return empty if query is empty

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT DISTINCT venue_name
            FROM public.connects
            WHERE venue_name ILIKE %s
            """, [f'%{query}%']
        )
        venue_names = [{'name': row[0]} for row in cursor.fetchall()]

    return JsonResponse({'venue_names': venue_names})


def fetch_venue_address(request):
    print('Inside the venue address')
    venue_name = request.GET.get('venue_name', '').strip()
    if not venue_name:
        return JsonResponse({'venue_address': ''})  # Return empty if no venue name is provided

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT venue_address
            FROM public.connects
            WHERE venue_name = %s
            LIMIT 1
            """, [venue_name]
        )
        result = cursor.fetchone()
        venue_address = result[0] if result else ''

    return JsonResponse({'venue_address': venue_address})


def save_new_row(request):
    if request.method == 'POST':
        job_reference_no = request.POST.get('jobReferenceNo')
        title = request.POST.get('title')
        client_name = request.POST.get('client_name')
        venue_address = request.POST.get('venue_address')
        status = request.POST.get('status')
        crew_type = request.POST.get('crew_type')
        no_of_container = request.POST.get('no_of_container')
        employee = request.POST.get('prep_sheet')
        setup_date = request.POST.get('setup_date')
        rehearsal_date = request.POST.get('rehearsal_date')
        start_date = request.POST.get('start_date')
        end_date = request.POST.get('end_date')
        category_name = request.POST.get('category_name')
        equipment_id = request.POST.get('equipment_name')
        quantity = request.POST.get('quantity')
        number_of_days = request.POST.get('number_of_days')
        amount = request.POST.get('amount')

        print('Received details:', job_reference_no, title, client_name, venue_address, status, crew_type,
              no_of_container, employee, setup_date, rehearsal_date, start_date, end_date, category_name,
              equipment_id, quantity, number_of_days, amount)

        if not (job_reference_no and title and client_name and venue_address and status and setup_date and
                rehearsal_date and start_date and end_date and category_name and equipment_id and quantity and
                number_of_days and amount):
            return JsonResponse({'success': False, 'error': 'Missing required fields'})

        try:
            print('Inside the try block of save new row')
            with connection.cursor() as cursor:
                print('Inside the cursor')

                # Fetch equipment_name from equipment_list table using equipment_id
                cursor.execute("""
                    SELECT equipment_name FROM equipment_list WHERE id = %s;
                """, [equipment_id])
                equipment_name_row = cursor.fetchone()
                if not equipment_name_row:
                    return JsonResponse({'success': False, 'error': 'Equipment ID not found'})
                equipment_name = equipment_name_row[0]

                print('Fetched equipment_name:', equipment_name)

                cursor.execute("""
                    INSERT INTO public.jobs (job_reference_no, title, client_name, venue_address, status, crew_type,
                                             no_of_container, employee, setup_date, rehearsal_date, show_start_date,
                                             show_end_date, category_name, equipment_name, quantity, number_of_days,
                                             amount)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id;
                """,
                               [job_reference_no, title, client_name, venue_address, status, crew_type, no_of_container,
                                employee, setup_date, rehearsal_date, start_date, end_date, category_name,
                                equipment_name, quantity, number_of_days, amount])
                print('Cursor executed successfully', category_name, equipment_name)
                new_job_id = cursor.fetchone()[0]
                print('New job ID:', new_job_id)
            return JsonResponse({'success': True, 'new_job_id': new_job_id})
        except Exception as e:
            print('Exception occurred:', str(e))
            traceback.print_exc()
            return JsonResponse({'success': False, 'error': str(e)})
    return JsonResponse({'success': False, 'error': 'Invalid request method'})


def get_new_row_data(request):
    with connection.cursor() as cursor:
        # Execute the PostgreSQL function to fetch the equipment name
        cursor.execute("SELECT equipment_name FROM equipment_list")
        equipment_name = cursor.fetchone()[0]  # Fetch the first row and the first column value

    # Create a dictionary containing the equipment details
    data = {
        'equipment_name': equipment_name,
        'quantity': 1,  # Example quantity, replace with actual data
        'startdate': '2024-01-02',  # Example start date, replace with actual data
        'enddate': '2025-01-04'  # Example end date, replace with actual data
    }

    return JsonResponse(data)


def fetch_master_categories(request):
    if request.method == 'GET':
        with connection.cursor() as cursor:
            cursor.execute("SELECT category_id, category_name FROM master_category ORDER BY category_name")
            master_categories = cursor.fetchall()
            master_categories_list = [{'category_id': row[0], 'category_name': row[1]} for row in master_categories]
            print(master_categories_list)
        return JsonResponse({'master_categories': master_categories_list})


def fetch_equipment_names(request):
    if request.method == 'GET':
        category_name = request.GET.get('category_name')
        if category_name:
            with connection.cursor() as cursor:

                # Select distinct equipment names from equipment_list with corresponding stock in stock_details
                cursor.execute("""
                    SELECT DISTINCT ON (e.equipment_name) e.id, e.equipment_name
                    FROM equipment_list e
                    JOIN stock_details s ON e.id = s.equipment_id
                    WHERE e.category_type = %s AND s.unit > 0
                    ORDER BY e.equipment_name, s.id DESC
                    """, [category_name])
                equipment_names = cursor.fetchall()
                equipment_names_list = [{'id': row[0], 'equipment_name': row[1]} for row in equipment_names]
                return JsonResponse({'equipment_names': equipment_names_list})
        else:
            return JsonResponse({'error': 'Category name is required.'}, status=400)
    else:
        return JsonResponse({'error': 'Invalid request method.'}, status=405)


@csrf_exempt
def check_equipment_in_temp(request):
    if request.method == 'POST':
        title = request.POST.get('title')
        equipment_id = request.POST.get('equipment_name')  # assuming equipment_name is the equipment ID

        logger.info(f"Received title: {title}, equipment_id: {equipment_id}")

        if equipment_id and title:
            # Fetch the equipment name based on the equipment ID
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT equipment_name
                    FROM equipment_list
                    WHERE id = %s
                """, [equipment_id])
                equipment_name_result = cursor.fetchone()

                if equipment_name_result:
                    equipment_name = equipment_name_result[0]

                    # Check if the equipment name and title exist in the temp table
                    cursor.execute("""
                        SELECT 1
                        FROM temp
                        WHERE equipment_name = %s
                          AND title = %s
                    """, [equipment_name, title])
                    exists = cursor.fetchone()

                    if exists:
                        return JsonResponse({'exists': True, 'equipment_name': equipment_name})
                    else:
                        return JsonResponse({'exists': False, 'equipment_name': equipment_name})
                else:
                    return JsonResponse({'error': 'Invalid equipment ID.'}, status=400)
        else:
            return JsonResponse({'error': 'Both equipment ID and job reference number are required.'}, status=400)
    else:
        return JsonResponse({'error': 'Invalid request method.'}, status=405)


def fetch_rental_price(request):
    equipment_id = request.GET.get('equipment_id')
    if equipment_id:
        with connection.cursor() as cursor:
            cursor.execute("SELECT rental_price FROM stock_details WHERE equipment_id = %s", [equipment_id])
            row = cursor.fetchone()
            if row:
                rental_price = row[0]
                return JsonResponse({'rental_price': rental_price})
            else:
                return JsonResponse({'error': 'Stock details not found'}, status=404)
    return JsonResponse({'error': 'Invalid request'}, status=400)


def insert_data(request):
    if request.method == 'POST':
        title = request.POST.get('title')
        client_name = request.POST.get('client_name')
        contact_person_name = request.POST.get('contact_person_name')
        contact_person_number = request.POST.get('contact_person_number')
        venue_address = request.POST.get('venue_address')
        status = request.POST.get('status')
        crew_type = request.POST.get('crew_type')
        no_of_container = request.POST.get('no_of_container')
        employee = request.POST.get('employee')
        setup_date = request.POST.get('setup_date')
        rehearsal_date = request.POST.get('rehearsal_date')
        start_date = request.POST.get('start_date')
        end_date = request.POST.get('end_date')
        total_days = request.POST.get('total_days')
        amount_row = request.POST.get('amount_row')
        discount = request.POST.get('discount')
        discount_amount = request.POST.get('discount_amount')
        total_amount = request.POST.get('total_amount')
        category_name = request.POST.get('category_name')
        equipment_name = request.POST.get('equipment_name')
        quantity = request.POST.get('quantity')
        number_of_days = request.POST.get('number_of_days')
        amount = request.POST.get('amount')

        print('Received employee:', employee)

        employee_list = employee.split(',') if employee else []

        print('Processed employee_list:', employee_list)

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT insert_row_data(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                [None, title, client_name, contact_person_name, contact_person_number, venue_address, status, crew_type,
                 no_of_container, employee,
                 setup_date, rehearsal_date, start_date,
                 end_date, total_days, amount_row, discount, discount_amount, total_amount, category_name,
                 equipment_name, quantity, number_of_days, amount])

            print('insert data success:', employee)

        return JsonResponse({'message': 'Data inserted successfully'}, status=201)

    return JsonResponse({'error': 'Method not allowed'}, status=405)


def get_employee_name(request):
    if request.method == 'GET':
        with connection.cursor() as cursor:
            cursor.execute("SELECT DISTINCT id, name FROM employee")
            employee_names = cursor.fetchall()
            print('Fetch employee names:', employee_names)
            employee_names_list = [{'id': row[0], 'name': row[1]} for row in employee_names]
            print('Fetch employee Names with id:', employee_names_list)
        return JsonResponse({'employee_names': employee_names_list})


def delete_row_from_temp_table(request):
    print('inside the delete row table')
    if request.method == 'POST':
        print('inside the post method')
        category_name = request.POST.get('category')
        equipment_name = request.POST.get('equipment')
        quantity = request.POST.get('quantity')
        number_of_days = request.POST.get('days')
        amount = request.POST.get('amount')

        print('fetch the data:', category_name, equipment_name, quantity, number_of_days, amount)

        try:
            print('inside the try block')
            with connection.cursor() as cursor:
                print('inside the cursor and cursor in row')
                cursor.execute(
                    "DELETE FROM temp WHERE quantity = %s AND number_of_days = %s AND amount = %s",
                    [quantity, number_of_days, amount]
                )
                print('Delete the row:', category_name, equipment_name, quantity, number_of_days, amount)
            return JsonResponse({'message': 'Row deleted successfully'}, status=200)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    else:
        return JsonResponse({'error': 'Invalid request method'}, status=400)


def jobs_list(request):
    print('Received Jobs List')
    jobs_listing = []
    processed_job_reference_nos = set()
    try:
        print('inside the get job list')
        with connection.cursor() as cursor:
            print('inside the cursor connection object')
            cursor.callproc('jobs_master_list',
                            ['READ', None, None, None, None, None, None, None, None, None, None, None, None, None, None,
                             None, None, None, None, None, None, None, None, None, None, None, None, None])
            jobs = cursor.fetchall()
            print('Fetch the jobs:', jobs)

            columns = [col[0] for col in cursor.description]
            for job in jobs:
                job_dict = dict(zip(columns, job))
                job_reference_no = job_dict.get('job_reference_no')
                if job_reference_no not in processed_job_reference_nos:
                    jobs_listing.append(job_dict)
                    processed_job_reference_nos.add(job_reference_no)

    except Exception as e:
        print("Error fetching Jobs list:", e)
        return JsonResponse({'error': str(e)}, status=500)

    return JsonResponse(jobs_listing, safe=False)


def get_status_counts(request):
    with connection.cursor() as cursor:
        # cursor.execute("SELECT COUNT(*) FROM public.jobs WHERE status = 'Perfoma';")
        cursor.execute(
            "SELECT COUNT(*) FROM (SELECT job_reference_no, status FROM public.temp WHERE status = 'Porforma' GROUP BY  job_reference_no, status) AS unique_perfoma;")
        perfoma_count = cursor.fetchone()[0]
        print('Porforma status count:', perfoma_count)

        cursor.execute(
            "SELECT COUNT(*) FROM (SELECT job_reference_no, status FROM public.temp WHERE status = 'Prepsheet' GROUP BY job_reference_no, status) AS unique_prepsheets;")
        prepsheet_count = cursor.fetchone()[0]
        print('Prepsheet Status count:', prepsheet_count)

        cursor.execute(
            "SELECT COUNT(*) FROM (SELECT job_reference_no, status FROM public.temp WHERE status = 'Quotation' GROUP BY job_reference_no, status) AS unique_quats;")
        quatation_count = cursor.fetchone()[0]
        print('Quatation Status count:', quatation_count)

        cursor.execute(
            "SELECT COUNT(*) FROM (SELECT job_reference_no, status FROM public.temp WHERE status = 'Delivery Challan' GROUP BY job_reference_no, status) AS unique_deliveries;")
        deliveryChallan_count = cursor.fetchone()[0]
        print('Delivery Challan Status count:', deliveryChallan_count)

    data = {
        'perfoma_count': perfoma_count,
        'prepsheet_count': prepsheet_count,
        'quatation_count': quatation_count,
        'deliveryChallan_count': deliveryChallan_count,
    }

    return JsonResponse(data)


def update_jobs(request, id):
    if request.method == 'POST':
        print('Received POST request to update Jobs details')
        job_reference_no = request.POST.get('jobReferenceNo')
        title = request.POST.get('title')
        status = request.POST.get('status')
        print(id, job_reference_no, title, status)
        try:
            print('inside the try block')
            with connection.cursor() as cursor:
                print('inside the cursor')
                cursor.callproc('jobs_master_list',
                                ['UPDATE', id, job_reference_no, title, None, None, status, None, None, None, None,
                                 None, None, None, None, None, None, None, None])
                print('inside the callproc', id, status)
                updated_jobs_id = cursor.fetchone()
                print(updated_jobs_id)
            return JsonResponse(
                {'message': 'Jobs details updated successfully', 'updated_jobs_id': updated_jobs_id})
        except Exception as e:
            return JsonResponse({'error': 'Failed to update jobs details', 'exception': str(e)})
    else:
        return JsonResponse({'error': 'Invalid request method'})


@csrf_exempt
def update_job_details(request, id):
    print('Inside the Job Details with ID:', id)
    if request.method == 'POST':
        print('Fetch the POST method')
        try:
            print('Inside the try block')
            data = json.loads(request.body)
            category_name = data.get('category_name')
            equipment_name = data.get('equipment_name')
            quantity = data.get('quantity')
            number_of_days = data.get('number_of_days')
            amount = data.get('amount')
            print('Fetch the DATA:', data, category_name, equipment_name, quantity, number_of_days, amount)

            with connection.cursor() as cursor:
                print('inside the cursor block')
                cursor.execute("""
                    UPDATE job_details
                    SET category_name = %s,
                        equipment_name = %s,
                        quantity = %s,
                        number_of_days = %s,
                        amount = %s
                    WHERE id = %s
                """, [category_name, equipment_name, quantity, number_of_days, amount, id])
                print('Updated the DATA:', id, category_name, equipment_name, quantity, number_of_days, amount)

            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    else:
        return JsonResponse({'success': False, 'error': 'Invalid request method'})


def job_details_page(request):
    username = request.session.get('username')
    return render(request, 'product_tracking/job_details.html', {'username': username})


def get_job_details(request):
    job_id = request.GET.get('jobId')

    if job_id:
        try:
            with connection.cursor() as cursor:
                # Fetch job details from jobs table
                cursor.execute("""
                    SELECT j.id, j.title, j.client_name, j.contact_person_name,
			            j.contact_person_number, j.venue_address, j.status,
                        j.crew_type, j.no_of_container, j.employee,
                        j.setup_date, j.rehearsal_date, j.show_start_date, j.show_end_date,
                        j.total_days, j.amount_row, j.discount, j.amount_after_discount, j.total_amount
                    FROM public.jobs j
                    WHERE j.id = %s
                """, [job_id])
                job_row = cursor.fetchone()
                print('Fetch the job Row:', job_row)

                if job_row:
                    job_data = {
                        'id': job_row[0],
                        'title': job_row[1],
                        'client_name': job_row[2],
                        'contact_person_name': job_row[3],
                        'contact_person_number': job_row[4],
                        'venue_address': job_row[5],
                        'status': job_row[6],
                        'crew_type': job_row[7],
                        'no_of_container': job_row[8],
                        'employee': job_row[9],
                        'setup_date': job_row[10].strftime('%Y-%m-%d') if job_row[10] else None,
                        'rehearsal_date': job_row[11].strftime('%Y-%m-%d') if job_row[11] else None,
                        'show_start_date': job_row[12].strftime('%Y-%m-%d') if job_row[12] else None,
                        'show_end_date': job_row[13].strftime('%Y-%m-%d') if job_row[13] else None,
                        'total_days': job_row[14],
                        'amount_row': job_row[15],
                        'discount': job_row[16],
                        'amount_after_discount': job_row[17],
                        'total_amount': job_row[18],
                    }
                    print('Fetch the Data:', job_data)
                    # Fetch job_details related to the job_id
                    cursor.execute("""
                        SELECT d.id, d.category_name, d.equipment_name, d.quantity, d.number_of_days, d.amount
                        FROM public.job_details d
                        WHERE d.job_id = %s
                    """, [job_id])
                    job_details_rows = cursor.fetchall()

                    job_details_data = []
                    for row in job_details_rows:
                        job_detail_data = {
                            'id': row[0],  # Include id field
                            'category_name': row[1],
                            'equipment_name': row[2],
                            'quantity': row[3],
                            'number_of_days': row[4],
                            'amount': row[5]
                        }
                        print('Fetch the DATA:', job_detail_data)
                        job_details_data.append(job_detail_data)

                    return JsonResponse({'success': True, 'job_data': job_data, 'job_details': job_details_data})
                else:
                    return JsonResponse({'success': False, 'error': 'Job details not found'}, status=404)

        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=500)

    return JsonResponse({'success': False, 'error': 'Invalid request'})


def delete_job_row(request, job_id):
    if request.method == 'POST':
        try:
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM public.jobs WHERE id = %s;", [job_id])
                return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})

    return JsonResponse({'success': False, 'error': 'Invalid request method'})


def delete_jobs(request, id):
    print('Inside the delete jobs', id)
    if request.method == 'POST':
        print('Check the POST method')
        with connection.cursor() as cursor:
            print('Inside the cursor connection object')
            cursor.callproc('jobs_master_list',
                            [
                                'DELETE',  # operation
                                id,  # in_id
                                None,  # in_job_reference_no
                                None,  # in_title
                                None,  # in_client_name
                                None,  # in_contact_person_name
                                None,  # in_contact_person_number
                                None,  # in_venue_address
                                None,  # in_status
                                None,  # in_crew_type
                                None,  # in_no_of_container
                                None,  # in_employee
                                None,  # in_setup_date
                                None,  # in_rehearsal_date
                                None,  # in_show_start_date
                                None,  # in_show_end_date
                                None,  # in_total_days
                                None,  # in_amount_row
                                None,  # in_discount
                                None,  # in_amount_after_discount
                                None,  # in_total_amount
                                [],  # in_category_id
                                [],  # in_equipment_id
                                [],  # in_quantity
                                [],  # in_number_of_days
                                [],  # in_amount
                                None,  # in_created_by
                                None  # in_created_date
                            ])
            print('Check the data')
        return JsonResponse({'message': 'Job deleted successfully'}, status=200)
    else:
        return JsonResponse({'error': 'Invalid request method'}, status=400)


def add_connects(request):
    if request.method == 'POST':
        c_type = request.POST.get('type')
        created_by = int(request.session.get('user_id'))
        created_date = datetime.now()
        c_status = request.POST.get('status')

        if c_type == 'Company':
            c_company_name = request.POST.get('company_name')
            c_gst_no = request.POST.get('gst_no')
            c_pan_no = request.POST.get('pan_no')
            c_contact_person_name = request.POST.get('person_name')
            c_contact_person_no = request.POST.get('person_no')  # Ensure this value is correct
            c_contact_email = request.POST.get('contact_email')
            c_billing_address = request.POST.get('billing_address')
            c_office_address = request.POST.get('office_address')
            c_social_no = request.POST.get('social_no')
            c_city = request.POST.get('city')
            c_country = request.POST.get('country')
            c_post_code = request.POST.get('post_code')
            c_company, c_name, c_email, c_mobile, c_address, c_venue_name, c_venue_address, c_client_name, c_client_address, c_client_mobile_no = (
                None, None, None, None, None, None, None, None, None, None)

            print('Fetch the details of company:', c_contact_person_no)
        elif c_type == 'Individual':
            c_name = request.POST.get('name')
            c_email = request.POST.get('email')
            c_mobile = request.POST.get('mobile_no')
            c_address = request.POST.get('address')
            c_city = request.POST.get('city')
            c_country = request.POST.get('country')
            c_post_code = request.POST.get('post_code')
            c_social_no = request.POST.get('social_no')
            c_company = request.POST.get('company')
            (c_company_name, c_gst_no, c_pan_no, c_contact_person_name, c_contact_person_no, c_contact_email,
             c_billing_address, c_office_address, c_venue_name,
             c_venue_address, c_client_name, c_client_address,
             c_client_mobile_no) = None, None, None, None, None, None, None, None, None, None, None, None, None
        elif c_type == 'Venue':
            c_venue_name = request.POST.get('venue_name')
            c_venue_address = request.POST.get('venue_address')
            c_city = request.POST.get('city')
            c_country = request.POST.get('country')
            c_post_code = request.POST.get('post_code')
            (c_company_name, c_name, c_email, c_mobile, c_address, c_social_no, c_company, c_gst_no, c_pan_no,
             c_contact_person_name, c_contact_person_no, c_contact_email,
             c_billing_address,
             c_office_address, c_client_name, c_client_address,
             c_client_mobile_no) = None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None
        else:
            c_client_name = request.POST.get('client_name')
            c_client_address = request.POST.get('client_address')
            c_client_mobile_no = request.POST.get('client_mobile_no')
            c_city = request.POST.get('city')
            c_country = request.POST.get('country')
            c_post_code = request.POST.get('post_code')
            (c_company_name, c_name, c_email, c_mobile, c_address, c_social_no, c_company, c_gst_no, c_pan_no,
             c_contact_person_name, c_contact_person_no, c_contact_email,
             c_billing_address,
             c_office_address, c_venue_name,
             c_venue_address) = None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None

        print('Fetch the correct c_person Number:', c_contact_person_name, c_contact_person_no)
        try:
            print('Fetch the try', )
            with connection.cursor() as cursor:
                print('Check connection cursor object')
                cursor.callproc('connect_master', ['CREATE', None, c_type, c_name, c_email, c_mobile, c_address, c_city,
                                                   c_country, c_post_code, created_by, created_date, c_status,
                                                   c_company_name, c_gst_no, c_pan_no, c_contact_person_name,
                                                   c_contact_person_no, c_contact_email, c_billing_address,
                                                   c_office_address, c_social_no, c_company, c_venue_name,
                                                   c_venue_address, c_client_name, c_client_address,
                                                   c_client_mobile_no])
                print('call the callproc')

                columns = [col[0] for col in cursor.description]
                print('Fetch the ID:', columns)
                result_set = [dict(zip(columns, row)) for row in cursor.fetchall()]
                print('Fetch the Details:', result_set)

                # Check the result set and retrieve the result_message
                result_message = result_set[0].get('result_message', None) if result_set else None

                if result_message == 'Connects added successfully.':
                    return redirect('add_connects')
                else:
                    error_message = 'Error occurred while adding connects.'
                    return render(request, 'product_tracking/contacts.html', {'error_message': error_message})
        except IntegrityError:
            error_message = 'Error occurred while adding connects.'
            return render(request, 'product_tracking/contacts.html', {'error_message': error_message})
    else:
        username = None
        if request.user.is_authenticated:
            username = request.user.username
    # If the request method is GET, render the form
    return render(request, 'product_tracking/contacts.html', {'username': username})


def company_dropdown_view(request):
    if request.method == 'GET':
        # Call the stored procedure to fetch the connect records
        with connection.cursor() as cursor:
            cursor.callproc('connect_master', [
                'READ',  # operation
                None,  # in_id
                None,  # in_type
                None,  # in_name
                None,  # in_email
                None,  # in_mobile
                None,  # in_address
                None,  # in_city
                None,  # in_country
                None,  # in_post_code
                None,  # in_created_by
                None,  # in_created_date
                None,  # in_status
                None,  # in_company_name
                None,  # in_gst
                None,  # in_pan
                None,  # in_contact_person_name
                None,  # in_contact_person_no
                None,  # in_contact_email
                None,  # in_billing_address
                None,  # in_office_address
                None,  # in_social_no
                None  # in_company

            ])
            result = cursor.fetchall()
            columns = [col[0] for col in cursor.description]

        # Convert the result to a list of dictionaries
        data = [dict(zip(columns, row)) for row in result]

        # Return the result as JSON
        return JsonResponse(data, safe=False)
    else:
        return JsonResponse({'error': 'Invalid request method'}, status=400)


def connect_list(request):
    with connection.cursor() as cursor:
        cursor.callproc("connect_master",
                        ["READ", None, None, None, None, None, None, None, None, None, None, None, None,
                         None, None, None, None, None, None, None, None, None, None, None, None, None, None, None])

        connects_list = cursor.fetchall()

    # Convert the result into a list of dictionaries
    item_listing = []
    for item in connects_list:
        # Adjust the indexing based on the actual columns returned
        created_date_time = item[10].strftime('%d-%m-%Y')
        item_data = {
            'id': item[0],
            'type': item[1] if len(item) > 1 and item[1] else None,
            'city': item[6] if len(item) > 6 and item[6] else None,
            'country': item[7] if len(item) > 7 and item[7] else None,
            'post_code': item[8] if len(item) > 8 and item[8] else None,
            'created_by': item[9] if len(item) > 9 and item[9] else None,
            'created_date_time': created_date_time,
            'status': item[11] if len(item) > 11 and item[11] else None,
        }
        # Add type-specific fields based on the type
        if item_data['type'] == 'Individual':
            item_data.update({
                'name': item[2],
                'email': item[3],
                'mobile': item[4],
                'address': item[5],
            })
        elif item_data['type'] == 'Company':
            item_data.update({
                'company_name': item[12],
                'gst_no': item[13],
                'pan_no': item[14],
                'contact_person_name': item[15],
                'contact_person_no': item[16],
                'contact_email': item[17],
                'billing_address': item[18],
                'office_address': item[19],
                'social_no': item[20],
            })
        elif item_data['type'] == 'Venue':
            item_data.update({
                'venue_name': item[22],  # Adjust based on your database structure
                'venue_address': item[23],  # Adjust based on your database structure
            })
        elif item_data['type'] == 'Client':
            item_data.update({
                'client_name': item[24],  # Adjust based on your database structure
                'client_address': item[25],  # Adjust based on your database structure
                'client_mobile_no': item[26],
            })
        item_listing.append(item_data)

    return JsonResponse(item_listing, safe=False)


def update_connect(request, id):
    print('inside the update function')
    if request.method == 'POST':
        print('inside the POST method')
        data = json.loads(request.body)
        type = data.get('type')
        name = data.get('name')
        email = data.get('email')
        mobile = data.get('mobile')
        address = data.get('address')
        city = data.get('city')
        country = data.get('country')
        post_code = data.get('post_code')

        print(id, type, name, email, mobile, address)

        try:
            print('inside the try block')
            with connection.cursor() as cursor:
                print('inside the cursor')
                cursor.callproc('connect_master',
                                ['UPDATE', id, type, name, email, mobile, address, city, country, post_code, None, None,
                                 None, None, None,
                                 None, None, None, None, None, None, None, None, None, None, None, None, None])
                print('call the callproc object')
                updated_id = cursor.fetchone()
                print('Updated ID:', updated_id)
            return JsonResponse(
                {'message': 'Contact details updated successfully', 'updated_id': updated_id})
        except Exception as e:
            print('Exception:', str(e))
            return JsonResponse({'error': 'Failed to update contact details', 'exception': str(e)})
    else:
        return JsonResponse({'error': 'Invalid request method'})


def delete_connect(request, id):
    if request.method == 'POST':
        # Call the stored procedure to delete the connect record
        with connection.cursor() as cursor:
            cursor.callproc('connect_master',
                            ['DELETE', id, None, None, None, None, None, None, None, None, None, None, None, None, None,
                             None, None, None, None, None, None, None, None, None, None, None, None, None])
        # Return a success response
        return JsonResponse({'message': 'Contact deleted successfully'}, status=200)
    else:
        # Return an error response for invalid request method
        return JsonResponse({'error': 'Invalid request method'}, status=400)


def warehouse_master(request):
    username = request.session.get('username')
    return render(request, 'product_tracking/warehouse-master.html', {'username': username})


def add_warehouse_master(request):
    if request.method == 'POST':
        company_name = request.POST.get('warehouseCompanyName')
        phone_no = request.POST.get('warehousePhoneNo')
        address = request.POST.get('warehouseName')

        with connection.cursor() as cursor:
            cursor.callproc('warehouse_master', ['CREATE', None, company_name, phone_no, address])
            warehouse = cursor.fetchall()
            print('Fetch warehouse:', warehouse)
            return redirect('warehouse_master')

    return render(request, 'product_tracking/warehouse-master.html', )


def warehouse_master_list(request):
    warehouse_master_listing = []
    try:
        with connection.cursor() as cursor:
            cursor.callproc('warehouse_master',
                            ['READ', None, None, None, None])
            rows = cursor.fetchall()

            for row in rows:
                warehouse_master_listing.append({
                    'id': row[0],
                    'company_name': row[1],
                    'phone_no': row[2],
                    'address': row[3],
                })
    except Exception as e:
        print("Error fetching Warehouse Master List:", e)
    return JsonResponse(warehouse_master_listing, safe=False)


def update_warehouse(request, id):
    if request.method == 'POST':
        print('Received POST request to update Jobs details')
        company_name = request.POST.get('jobReferenceNo')
        phone_no = request.POST.get('title')
        address_name = request.POST.get('valuesShow')
        print(id, company_name, phone_no, address_name)
        try:
            print('inside the try block')
            with connection.cursor() as cursor:
                print('inside the cursor')
                cursor.callproc('warehouse_master',
                                ['UPDATE', id, company_name, phone_no, address_name])
                print('inside the callproc', id, address_name)
                updated_jobs_id = cursor.fetchone()
                print(updated_jobs_id)
            return JsonResponse(
                {'message': 'Jobs details updated successfully', 'updated_jobs_id': updated_jobs_id})
        except Exception as e:
            return JsonResponse({'error': 'Failed to update jobs details', 'exception': str(e)})
    else:
        return JsonResponse({'error': 'Invalid request method'})


def delete_warehouse_master(request, id):
    if request.method == 'POST':
        with connection.cursor() as cursor:
            cursor.callproc('warehouse_master', ['DELETE', id, None, None, None])
        return JsonResponse({'message': 'Job deleted successfully'}, status=200)

    return JsonResponse({'error': 'Invalid request method'}, status=400)


def company_name_dropdown(request):
    with connection.cursor() as cursor:
        cursor.execute("SELECT id, name FROM public.company_master")
        companies = cursor.fetchall()

    company_list = [{'id': row[0], 'name': row[1]} for row in companies]
    return JsonResponse(company_list, safe=False)


def company_master(request):
    if request.method == 'POST':
        # Log data for debugging
        print("Received POST data:", request.POST)
        print("Received FILES data:", request.FILES)

        name = request.POST.get('companyName')
        gst_no = request.POST.get('companyGstNo')
        email = request.POST.get('companyEmail')
        company_logo = request.FILES.get('companyLogo')
        address = request.POST.get('companyAddress')

        # Assuming you're using Cloudinary, adjust the size limits as needed
        company_logo_attachment_url = None
        if company_logo:
            # Check file size (adjust as per your requirement)
            if company_logo.size < 4000 or company_logo.size > 12288:  # Example: 5KB to 12KB
                return JsonResponse({'error': 'Company logo size must be between 5KB and 12KB.'}, status=400)

            # Upload the file to Cloudinary (folder path can be customized)
            upload_result = cloudinary.uploader.upload(company_logo, folder="company_logos/")

            # Get the URL of the uploaded file
            company_logo_attachment_url = upload_result['secure_url']

        try:
            with connection.cursor() as cursor:
                cursor.callproc('company_master',
                                ['CREATE', None, name, gst_no, email, company_logo_attachment_url, address])
                company = cursor.fetchall()
                print('Inserted values are:', company)
                return redirect('warehouse_master')
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            return render(request, 'product_tracking/index.html', {'error': 'An unexpected error occurred'})

    # If the request method is GET, render the form
    return render(request, 'product_tracking/warehouse-master.html', )


def company_master_list(request):
    company_master_listing = []
    try:
        with connection.cursor() as cursor:
            cursor.callproc('company_master',
                            ['READ', None, None, None, None, None, None])
            rows = cursor.fetchall()

            for row in rows:
                company_master_listing.append({
                    'id': row[0],
                    'name': row[1],
                    'gst_no': row[2],
                    'email': row[3],
                    'company_logo': row[4],
                    'address': row[5],
                })
    except Exception as e:
        print("Error fetching Company Master List:", e)
    return JsonResponse(company_master_listing, safe=False)


def update_company(request, id):
    if request.method == 'POST':
        name = request.POST.get('companyName')
        CompanyGstNo = request.POST.get('jobMail')
        companyEmailId = request.POST.get('companyEmailId')  # Ensure this matches the form input name
        company_address = request.POST.get('companyAddress')

        try:
            with connection.cursor() as cursor:
                cursor.callproc('company_master',
                                ['UPDATE', id, name, CompanyGstNo, companyEmailId, None, company_address])
                updated_company_id = cursor.fetchone()
            return JsonResponse(
                {'message': 'Company details updated successfully', 'updated_company_id': updated_company_id})
        except Exception as e:
            return JsonResponse({'error': 'Failed to update company details', 'exception': str(e)})
    else:
        return JsonResponse({'error': 'Invalid request method'})


def delete_company_master(request, id):
    if request.method == 'POST':
        with connection.cursor() as cursor:
            cursor.callproc('company_master', ['DELETE', id, None, None, None, None, None])
        return JsonResponse({'message': 'Company list deleted successfully'}, status=200)

    return JsonResponse({'error': 'Invalid request method'}, status=400)


def fetch_subcategory_name(request, subcategory_id):
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT id, name FROM public.sub_category
                WHERE id = %s
            """, [subcategory_id])
            row = cursor.fetchone()
            print('Fetch the sub category ID:', row)

        if row:
            subcategory_id, subcategory_name = row
            return JsonResponse({'subcategory_id': subcategory_id, 'subcategory_name': subcategory_name})
        else:
            return JsonResponse({'error': 'Subcategory not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def fetch_subcategory_type(request, subcategory_id):
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT type FROM public.sub_category
                WHERE id = %s
            """, [subcategory_id])
            row = cursor.fetchone()
            print('Fetch the subcategory type ID:', row)

        if row:
            subcategory_type = row[0]  # Extract the type from the tuple
            if isinstance(subcategory_type, str):  # Ensure it's a string
                return JsonResponse({'subcategory_type': subcategory_type})
            else:
                return JsonResponse({'error': 'Invalid type format'}, status=500)
        else:
            return JsonResponse({'error': 'Subcategory not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def get_category_type(request):
    if request.method == 'GET' and 'subcategory_id' in request.GET:
        subcategory_id = request.GET.get('subcategory_id')
        print('fetch the subcategory id of equipment name:', subcategory_id)

        # Fetch category_id from sub_category based on subcategory_id
        subcategory_query = """
            SELECT category_id FROM sub_category
            WHERE id = %s
        """
        with connection.cursor() as cursor:
            cursor.execute(subcategory_query, [subcategory_id])
            subcategory_row = cursor.fetchone()
            print('Fetch the sub category id:', subcategory_row)

            if subcategory_row:
                category_id = subcategory_row[0]
                print('Fetch the category ID:', category_id)

                # Fetch category_name from master_category based on category_id
                master_category_query = """
                    SELECT category_name FROM master_category
                    WHERE category_id = %s
                """
                cursor.execute(master_category_query, [category_id])
                master_category_row = cursor.fetchone()
                print('Fetch the master category row:', master_category_row)

                if master_category_row:
                    category_name = master_category_row[0]
                    print('Fetch the category name Details:', category_name)
                    return JsonResponse({'category_name': category_name})
                else:
                    return JsonResponse({'error': 'Category name not found for the category ID.'}, status=404)
            else:
                return JsonResponse({'error': 'Subcategory ID not found.'}, status=404)
    else:
        return JsonResponse({'error': 'Invalid request method or parameters.'}, status=400)


def fetch_stock_details(request):
    print('Fetch the category ID:')
    try:
        category_id = request.GET.get('category_id')
        print('Fetch the category ID:', category_id)

        # Step 1: Retrieve subcategory IDs based on category_id
        subcategory_ids = []
        if category_id:
            subcategory_query = """
                SELECT id 
                FROM sub_category 
                WHERE category_id = %s
            """
            with connection.cursor() as cursor:
                cursor.execute(subcategory_query, [category_id])
                subcategory_ids = [row[0] for row in cursor.fetchall()]

        # Step 2: Retrieve equipment IDs based on the retrieved subcategory IDs
        equipment_ids = []
        if subcategory_ids:
            equipment_query = """
                SELECT id 
                FROM equipment_list 
                WHERE sub_category_id IN %s
            """
            with connection.cursor() as cursor:
                cursor.execute(equipment_query, [tuple(subcategory_ids)])
                equipment_ids = [row[0] for row in cursor.fetchall()]

        # Step 3: Fetch stock details based on the retrieved equipment IDs
        stock_details_query = """
            SELECT sd.id, el.equipment_name, sd.vender_name, sd.purchase_date, sd.unit_price,
                   sd.rental_price, sd.reference_no, sd.attchment, sd.unit, sd.serial_no, sd.barcode_no,
                   el.sub_category_id, sc.name as sub_category_name, el.category_type, el.type, 
                   el.dimension_height, el.dimension_width, el.dimension_length, el.weight, el.volume,
                   el.hsn_no, el.country_origin, el.status
            FROM stock_details sd
            INNER JOIN equipment_list el ON sd.equipment_id = el.id
            INNER JOIN sub_category sc ON el.sub_category_id = sc.id
            WHERE sd.equipment_id IN %s
        """

        with connection.cursor() as cursor:
            if equipment_ids:
                cursor.execute(stock_details_query, [tuple(equipment_ids)])
            else:
                cursor.execute(stock_details_query, [[]])  # Ensure empty list to avoid SQL error

            rows = cursor.fetchall()
            stock_details = []
            for row in rows:
                stock_details.append({
                    'id': row[0],
                    'equipment_name': row[1],
                    'vender_name': row[2],
                    'purchase_date': row[3].strftime('%Y-%m-%d') if row[3] else None,
                    'unit_price': float(row[4]) if row[4] else 0.0,
                    'rental_price': float(row[5]) if row[5] else 0.0,
                    'reference_no': row[6],
                    'attchment': row[7],
                    'unit': row[8],
                    'serial_no': row[9],
                    'barcode_no': row[10],
                    'sub_category_id': row[11],
                    'sub_category_name': row[12],
                    'category_type': row[13],
                    'type': row[14],
                    'dimension_height': row[15],
                    'dimension_width': row[16],
                    'dimension_length': row[17],
                    'weight': row[18],
                    'volume': row[19],
                    'hsn_no': row[20],
                    'country_origin': row[21],
                    'status': row[22],
                })
            return JsonResponse(stock_details, safe=False)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def fetch_client_contact_number(request):
    print('Inside the fetch client contact number')
    client_name = request.GET.get('client_name')
    client_type = request.GET.get('client_type')
    print('Fetch the client Name:', client_name)
    print('Fetch the client Type:', client_type)

    with connection.cursor() as cursor:
        print('Check the connection cursor')
        if client_type == 'Company':
            cursor.execute("""
                SELECT contact_person_name, contact_person_no
                FROM connects
                WHERE company_name = %s AND type = %s
            """, [client_name, client_type])
        else:
            # Handle other cases if needed
            return JsonResponse({'contact_person_name': '', 'contact_person_no': ''})

        print('Check the cursor object is executed')
        result = cursor.fetchone()
        print('Fetch the contact number successfully', result)

    contact_person_name = result[0] if result else ''
    contact_person_no = result[1] if result else ''  # Add this line
    return JsonResponse(
        {'contact_person_name': contact_person_name, 'contact_person_no': contact_person_no})  # Update this line



@csrf_exempt
def check_stock_availability(request):
    if request.method == 'POST':
        equipment_id = request.POST.get('equipment_id')
        requested_quantity = int(request.POST.get('quantity'))

        print('Fetching the details:', equipment_id, requested_quantity)

        with connection.cursor() as cursor:
            # Count the number of barcodes where scan_flag is FALSE or NULL
            cursor.execute("""
                SELECT COALESCE(COUNT(barcode_no), 0)
                FROM public.stock_details
                WHERE equipment_id = %s AND (scan_flag IS NULL OR scan_flag = TRUE)
            """, [equipment_id])
            available_barcode_units = cursor.fetchone()[0]
            print('Available barcode units with scan_flag TRUE or NULL:', available_barcode_units)

            # Check if the requested quantity is available
            if requested_quantity > available_barcode_units:
                return JsonResponse({
                    'status': 'error',
                    'message': f'The requested quantity is not available. The total available stock is: {available_barcode_units}'
                })
            else:
                return JsonResponse({
                    'status': 'success',
                    'available_units': available_barcode_units
                })

    return JsonResponse({
        'status': 'error',
        'message': 'Invalid request method.'
    })


@csrf_exempt
def update_all_job_details(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            formData = data.get('formData', {})
            rows = data.get('rows', [])
            jobId = data.get('jobId')

            print('Fetch the form DATA:', formData, rows)

            with connection.cursor() as cursor:
                # Update the jobs table
                cursor.execute("""
                    UPDATE jobs
                    SET title = %s,
                        client_name = %s,
                        contact_person_name = %s,
                        contact_person_number = %s,
                        venue_address = %s,
                        status = %s,
                        crew_type = %s,
                        no_of_container = %s,
                        employee = %s,
                        setup_date = %s,
                        rehearsal_date = %s,
                        show_start_date = %s,
                        show_end_date = %s,
                        total_days = %s,
                        amount_row = %s,
                        discount = %s,
                        amount_after_discount = %s,
                        total_amount = %s
                    WHERE id = %s
                """, [
                    formData.get('title'),
                    formData.get('client_name'),
                    formData.get('contact_person_name'),
                    formData.get('contact_person_number'),
                    formData.get('venue_address'),
                    formData.get('status'),
                    formData.get('crew_type'),
                    formData.get('no_of_container'),
                    formData.get('employee'),
                    formData.get('setup_date'),
                    formData.get('rehearsal_date'),
                    formData.get('show_start_date'),
                    formData.get('show_end_date'),
                    formData.get('total_days'),
                    formData.get('amount_row'),
                    formData.get('discount'),
                    formData.get('amount_after_discount'),
                    formData.get('total_amount'),
                    jobId
                ])

                # Update the job_details table
                for row in rows:
                    jobDetailId = row.get('jobDetailId')
                    category_name = row.get('category_name')
                    equipment_name = row.get('equipment_name')
                    quantity = row.get('quantity')
                    number_of_days = row.get('number_of_days')
                    amount = row.get('amount')

                    cursor.execute("""
                        UPDATE job_details
                        SET category_name = %s,
                            equipment_name = %s,
                            quantity = %s,
                            number_of_days = %s,
                            amount = %s
                        WHERE id = %s
                    """, [category_name, equipment_name, quantity, number_of_days, amount, jobDetailId])

            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    else:
        return JsonResponse({'success': False, 'error': 'Invalid request method'})


@csrf_exempt
def save_job_details(request):
    if request.method == 'POST':
        job_id = request.POST.get('job_id')
        category_name = request.POST.get('category_name')
        equipment_id = request.POST.get('equipment_id')
        quantity = request.POST.get('quantity')
        number_of_days = request.POST.get('number_of_days')
        amount = request.POST.get('amount')

        try:
            with connection.cursor() as cursor:
                # Fetch the equipment_name based on equipment_id from equipment_list table
                cursor.execute("SELECT equipment_name FROM equipment_list WHERE id = %s", [equipment_id])
                equipment_name = cursor.fetchone()

                if not equipment_name:
                    return JsonResponse({'status': 'error', 'message': 'Equipment not found'}, status=404)

                # Insert the new row into the job_details table
                cursor.execute("""
                    INSERT INTO job_details (job_id, category_name, equipment_name, quantity, number_of_days, amount)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (job_id, category_name, equipment_name[0], quantity, number_of_days, amount))

            return JsonResponse({'status': 'success'}, status=200)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    else:
        return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=400)


@csrf_exempt
def delete_job_detail(request):
    if request.method == 'POST':
        job_detail_id = request.POST.get('jobDetailId')

        if not job_detail_id:
            return JsonResponse({'status': 'error', 'message': 'Job detail ID is required'})

        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    DELETE FROM job_details
                    WHERE id = %s
                """, [job_detail_id])

            return JsonResponse({'status': 'success', 'message': 'Row deleted successfully'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)})
    else:
        return JsonResponse({'status': 'error', 'message': 'Invalid request method'})


def fetch_events(request):
    # Extract month and year from query parameters
    month = request.GET.get('month')
    year = request.GET.get('year')

    # Default to current month and year if not provided
    if not month or not year:
        from datetime import datetime
        now = datetime.now()
        month = now.month
        year = now.year

    # Convert month and year to integers
    try:
        month = int(month)
        year = int(year)
    except ValueError:
        return JsonResponse({'error': 'Invalid month or year'}, status=400)

    # SQL query to fetch events based on month and year
    query = """
        SELECT event_id, venue, client_name, person_name, start_date, end_date, created_date
        FROM public.calender
        WHERE EXTRACT(MONTH FROM start_date) = %s AND EXTRACT(YEAR FROM start_date) = %s
    """

    with connection.cursor() as cursor:
        cursor.execute(query, [month, year])
        rows = cursor.fetchall()

        # Convert the rows to a list of dictionaries
        events_list = []
        for row in rows:
            created_date_time = row[6]
            if created_date_time:
                # Format the datetime to get the time part in 12-hour format with AM/PM
                created_date_time = created_date_time.strftime('%I:%M %p')  # %I = 12-hour clock, %p = AM/PM
            else:
                created_date_time = 'No time available'

            events_list.append({
                'event_id': row[0],
                'venue': row[1],
                'client_name': row[2],
                'person_name': row[3],
                'start_date': row[4].strftime('%Y-%m-%d'),
                'end_date': row[5].strftime('%Y-%m-%d') if row[5] else '',
                'created_date': created_date_time
            })

    return JsonResponse(events_list, safe=False)


def job_form(request):
    return render(request, 'product_tracking/jobs-form.html')


def add_job_test(request):
    return render(request, 'product_tracking/add-job.html')


def job_addition(request):
    username = request.session.get('username')
    return render(request, 'product_tracking/job-addition.html', {'username': username})


def fetch_equipment_detail_id(request):
    job_id = request.GET.get('jobId')
    print('Check the job id:', job_id)

    if job_id:
        print('Check the job id is working..')
        with connection.cursor() as cursor:
            print('Check the cursor object working')
            # Query to fetch only equipment_detail_id based on jobId (temp_id)
            cursor.execute("""
                SELECT equipment_detail_id
                FROM temp_equipment_details
                WHERE temp_id = %s
            """, [job_id])
            equipment_ids = cursor.fetchall()
            print('check the equipment ID:', equipment_ids)

            # Remove duplicates while preserving order
            seen = set()
            equipment_detail_ids = []
            for row in equipment_ids:
                id_value = row[0]
                if id_value not in seen:
                    seen.add(id_value)
                    equipment_detail_ids.append(id_value)

            print('Check the equipment details:', equipment_detail_ids)
            return JsonResponse({'equipment_detail_ids': equipment_detail_ids}, safe=False)

    return JsonResponse({'error': 'No jobId provided'}, status=400)


def fetch_crew_allocation_details(request, job_id):
    with connection.cursor() as cursor:
        cursor.callproc('fetch_crew_allocation_details', [job_id])
        rows = cursor.fetchall()

    crew_details = []
    for row in rows:
        full_image_path = row[6]  # This contains the full path to the image
        if full_image_path:
            # Extract only the filename
            image_filename = os.path.basename(full_image_path)
            # Construct the correct URL for the image
            image_url = settings.MEDIA_URL + 'profilepic/' + image_filename
        else:
            # Use a default image if no path is provided
            image_url = static('uploads/download.jpg')

        crew_details.append({
            'tca_id': row[0],
            'employee_id': row[1],
            'emp_id': row[2],
            'name': row[3],
            'email': row[4],
            'mobile_no': row[5],
            'image_url': image_url
        })

    return JsonResponse(crew_details, safe=False)


def update_transportation_details(request, job_id):
    if request.method == 'POST':
        with connection.cursor() as cursor:
            cursor.callproc('update_transportation_details_fn', [
                job_id,
                request.POST.get('driver_name', ''),
                request.POST.get('contact_number', ''),
                request.POST.get('vehicle_number', ''),
                request.POST.get('outside_driver_name', ''),
                request.POST.get('outside_contact_number', ''),
                request.POST.get('outside_vehicle_number', '')
            ])
        return JsonResponse({'status': 'success', 'message': 'Details updated successfully'})
    return JsonResponse({'status': 'error', 'message': 'Invalid request method'})


def fetch_inserted_row(request):
    temp_id = request.GET.get('temp_id')

    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT id, equipment_name, quantity
                FROM temp_equipment_details
                WHERE temp_id = %s
                ORDER BY id DESC LIMIT 1
            """, [temp_id])

            row = cursor.fetchone()

            if row:
                data = {
                    'id': row[0],
                    'equipment_name': row[1],
                    'quantity': row[2],
                }
                return JsonResponse({'status': 'success', 'data': data})
            else:
                return JsonResponse({'status': 'error', 'message': 'No data found'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


@csrf_exempt
def update_quantity(request):
    if request.method == 'POST':
        try:
            id = int(request.POST.get('id'))
            quantity = int(request.POST.get('quantity'))

            with connection.cursor() as cursor:
                cursor.execute("""
                    UPDATE temp_equipment_details
                    SET quantity = %s
                    WHERE id = %s
                """, [quantity, id])

            return JsonResponse({'status': 'success'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)})
    return JsonResponse({'status': 'error', 'message': 'Invalid request method'})


@csrf_exempt
def fetch_employee_names(request):
    query = request.GET.get('query', '').strip()
    if not query:
        return JsonResponse({'employee_names': []})  # Return empty if query is empty

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT id, name
            FROM public.employee
            WHERE name ILIKE %s
            """, [f'%{query}%']
        )
        employee_names = [{'id': row[0], 'name': row[1]} for row in cursor.fetchall()]

    return JsonResponse({'employee_names': employee_names})


def fetch_job_reference_no(request):
    temp_id = request.GET.get('temp_id')  # Get the temp_id from the request

    if not temp_id:
        return JsonResponse({'status': 'error', 'error': 'temp_id not provided'})

    try:
        with connection.cursor() as cursor:
            # Execute raw SQL query to fetch job_reference_no from temp table
            cursor.execute(
                "SELECT job_reference_no, title, setup_date, event_date, dismantle_date FROM temp WHERE id = %s",
                [temp_id])
            row = cursor.fetchone()
            print('Fetch the row of JOB REFERENCE NO:', row)

        if row:
            job_reference_no = row[0]  # Get the job_reference_no from the query result
            title = row[1]
            event_date = row[2]
            dismantle_date = row[3]
            return JsonResponse({'status': 'success', 'job_reference_no': job_reference_no, 'title': title,
                                 'event_date': event_date, 'dismantle_date': dismantle_date})
        else:
            return JsonResponse({'status': 'error', 'error': 'No record found for the provided temp_id'})

    except Exception as e:
        return JsonResponse({'status': 'error', 'error': str(e)})


def fetch_equipment_data(request):
    query = """
    WITH active_jobs AS (
        SELECT id
        FROM public.temp
        WHERE status = 'Delivery Challan' AND completion_flag = false
    ),
    assigned_quantities AS (
        SELECT ted.equipment_name, SUM(CAST(ted.quantity AS INTEGER)) AS total_assigned
        FROM public.temp_equipment_details ted
        JOIN active_jobs aj ON ted.temp_id = aj.id
        GROUP BY ted.equipment_name
    )
    SELECT
        e.equipment_name,
        COUNT(s.id) AS available_quantity,
        COALESCE(SUM(s.rental_price), 0) / NULLIF(COUNT(s.id), 0) AS rental_price,  -- Calculate average price
        COALESCE(aq.total_assigned, 0) AS assigned_quantity
    FROM
        public.equipment_list e
    LEFT JOIN
        public.stock_details s ON e.id = s.equipment_id
    LEFT JOIN
        assigned_quantities aq ON e.equipment_name = aq.equipment_name
    GROUP BY
        e.id, e.equipment_name, aq.total_assigned
    ORDER BY
        e.equipment_name
    """

    with connection.cursor() as cursor:
        print('Check the cursor connection')
        cursor.execute(query)
        rows = cursor.fetchall()
        print('Fetch the equipment DATA:', rows)

    # Convert the results to a list of dictionaries
    equipment_data = [
        {
            'equipment_name': row[0],
            'available_quantity': row[1] - (row[3] if row[3] is not None else 0),  # Subtract assigned quantity
            'rental_price': int(row[2]) if row[2] is not None else 0,  # Convert rental_price to integer
            'assigned_quantity': row[3] if row[3] is not None else 0  # Assigned quantity from temp_equipment_details
        }
        for row in rows
    ]
    print('Fetch the Equipment Data of Eq:', equipment_data)
    return JsonResponse({'data': equipment_data})


@csrf_exempt
def insert_equipment_details_test(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        equipment_list = data.get('equipment', [])
        temp_id = data.get('temp_id')  # Fetch temp_id from the request

        equipment_detail_ids = []  # List to store all new IDs
        existing_ids = []  # List to store existing IDs

        with connection.cursor() as cursor:
            # Fetch job_reference_no based on temp_id
            cursor.execute("SELECT job_reference_no FROM public.temp WHERE id = %s", [temp_id])
            job_reference_no = cursor.fetchone()
            if job_reference_no is None:
                return JsonResponse({'error': 'Invalid temp_id'}, status=400)
            job_reference_no = job_reference_no[0]
            print('job reference no:', job_reference_no)

            # Fetch all existing equipment_detail_id where it starts with the job_reference_no
            cursor.execute("""
                SELECT equipment_detail_id FROM public.temp_equipment_details
                WHERE equipment_detail_id LIKE %s
            """, [f"{job_reference_no}/%"])
            existing_ids = cursor.fetchall()
            print('Existing equipment detail IDs:', existing_ids)

            # Flatten the list of existing IDs
            existing_ids = [eid[0] for eid in existing_ids]

            # Create a map of location -> equipment_detail_id
            location_id_map = {eid[1]: eid[0] for eid in existing_ids}

            # Fetch all existing locations for the same job_reference_no
            cursor.execute("""
                SELECT location FROM public.temp_equipment_details
                WHERE equipment_detail_id LIKE %s
            """, [f"{job_reference_no}/%"])
            existing_locations = cursor.fetchall()
            existing_locations = [loc[0] for loc in existing_locations]  # Flatten the list

            # Initialize the sequence number
            if existing_ids:
                # Extract the last sequence number and increment it
                last_id = existing_ids[-1]  # Get last equipment_detail_id
                last_number = int(last_id.split('/')[-1])
                next_number = last_number + 1
            else:
                next_number = 1

            # Insert new equipment details
            for equipment in equipment_list:
                equipment_name = equipment['equipment_name']
                quantity = equipment['quantity']
                equipment_unit_price = equipment['equipment_unit_price']
                equipment_total = equipment['equipment_total']
                equipment_notes = equipment['equipment_notes']
                location = equipment.get('location', '')
                incharge = equipment.get('incharge', '')
                equipment_setup_date = equipment.get('equipment_setup_date', '')
                equipment_rehearsal_date = equipment.get('equipment_rehearsal_date', '')

                # Check if the location already exists and use the same equipment_detail_id
                if location in location_id_map:
                    equipment_detail_id = location_id_map[location]
                else:
                    # If the location is new, assign a new equipment_detail_id and increment next_number
                    equipment_detail_id = f"{job_reference_no}/{str(next_number).zfill(2)}"
                    next_number += 1
                    location_id_map[location] = equipment_detail_id  # Map new location to this new ID

                # Append the new equipment_detail_id to the list of all new IDs
                equipment_detail_ids.append(equipment_detail_id)

                # Insert into the database
                query = """
                    INSERT INTO public.temp_equipment_details
                    (temp_id, equipment_detail_id, equipment_name, quantity, equipment_unit_price, equipment_total, equipment_notes, location, incharge, equipment_setup_date, equipment_rehearsal_date)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """
                cursor.execute(query, [
                    temp_id, equipment_detail_id, equipment_name, quantity,
                    equipment_unit_price, equipment_total, equipment_notes, location,
                    incharge, equipment_setup_date, equipment_rehearsal_date
                ])

        # Combine existing and new IDs for response
        all_ids = existing_ids + equipment_detail_ids
        print('Fetch the all IDS:', all_ids)

        return JsonResponse({'message': 'Equipment details inserted successfully', 'equipment_detail_ids': all_ids},
                            status=200)

    return JsonResponse({'error': 'Invalid request'}, status=400)



def fetch_equipment_details_multiple(request):
    if request.method == "GET":
        equip_id = request.GET.get('equipId')
        print('Check the Equipment ID:', equip_id)

        if equip_id:
            print('Fetch the details')
            with connection.cursor() as cursor:
                print('Check the cursor connection is working')
                # Replace 'temp_equipment_details' with your table name and column names as needed
                cursor.execute("""
                    SELECT id, location, incharge, equipment_setup_date, equipment_rehearsal_date, 
                           equipment_name, quantity, equipment_unit_price, equipment_total, equipment_notes
                    FROM temp_equipment_details
                    WHERE equipment_detail_id = %s
                """, [equip_id])

                # Fetch all results from the query
                equipment_details = cursor.fetchall()
                print('Check the Details of Equipment:', equipment_details)

                if equipment_details:
                    # Convert fetched rows into a list of dictionaries
                    data = [
                        {
                            'id': detail[0],
                            'location': detail[1],
                            'incharge': detail[2],
                            'setup_date': detail[3],
                            'rehearsal_date': detail[4],
                            'equipment_name': detail[5],
                            'quantity': detail[6],
                            'unit_price': detail[7],
                            'total': detail[8],
                            'equipment_notes': detail[9]
                        }
                        for detail in equipment_details
                    ]
                    print('Check the correct DATA of Multiple Equipment Details:', data)
                    return JsonResponse({'status': 'success', 'data': data})
                else:
                    return JsonResponse({'status': 'error', 'message': 'No details found for this equipment.'})
        else:
            return JsonResponse({'status': 'error', 'message': 'Invalid equipment ID.'})

    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'})



def fetch_employee_names_equipment(request):
    query = request.GET.get('query', '')

    if query:
        with connection.cursor() as cursor:
            # Use parameterized query to prevent SQL injection
            cursor.execute("""
                SELECT id, name 
                FROM public.employee 
                WHERE name ILIKE %s 
                LIMIT 10
            """, ['%' + query + '%'])

            employees = cursor.fetchall()

        # Format the results as a list of dictionaries
        employee_list = [{'id': emp[0], 'name': emp[1]} for emp in employees]

        return JsonResponse(employee_list, safe=False)

    return JsonResponse([], safe=False)


def delete_equipment_id(request):
    print('Check the delete equipment id is working.')
    if request.method == 'POST':
        print('check the POST method is working')
        equip_id = request.POST.get('equipId')
        print('Check the Equip ID:', equip_id)

        # Delete the equipment row from the temp_equipment_details table
        with connection.cursor() as cursor:
            print('Check the cursor connection is done.')
            try:
                print('try block is working')
                cursor.execute("DELETE FROM temp_equipment_details WHERE id = %s", [equip_id])
                return JsonResponse({'status': 'success', 'message': 'Equipment deleted successfully'})
                print('Delete successfully equipment')
            except Exception as e:
                return JsonResponse({'status': 'error', 'message': str(e)})


def update_equipment_id(request):
    if request.method == 'POST':
        row_equip_id = request.POST.get('rowEquipId')
        element_equip_id = request.POST.get('elementEquipId')
        equipment_name = request.POST.get('equipment_name')
        quantity = int(request.POST.get('quantity', 0))
        unit_price = request.POST.get('unit_price')
        total = request.POST.get('total')
        equipment_notes = request.POST.get('equipment_notes_temp')
        location = request.POST.get('location')
        incharge = request.POST.get('incharge')
        setup_date = request.POST.get('setup_date')
        rehearsal_date = request.POST.get('rehearsal_date')

        # Step 1: Check the available quantity before updating
        try:
            with connection.cursor() as cursor:
                # Execute reference query to get available and assigned quantities
                cursor.execute("""
                    WITH active_jobs AS (
                        SELECT id
                        FROM public.temp
                        WHERE status = 'Delivery Challan' AND completion_flag = false
                    ),
                    assigned_quantities AS (
                        SELECT ted.equipment_name, SUM(CAST(ted.quantity AS INTEGER)) AS total_assigned
                        FROM public.temp_equipment_details ted
                        JOIN active_jobs aj ON ted.temp_id = aj.id
                        GROUP BY ted.equipment_name
                    )
                    SELECT
                        COUNT(s.id) AS available_quantity,
                        COALESCE(aq.total_assigned, 0) AS assigned_quantity
                    FROM
                        public.equipment_list e
                    LEFT JOIN
                        public.stock_details s ON e.id = s.equipment_id
                    LEFT JOIN
                        assigned_quantities aq ON e.equipment_name = aq.equipment_name
                    WHERE e.equipment_name = %s
                    GROUP BY
                        e.equipment_name, aq.total_assigned
                """, [equipment_name])

                result = cursor.fetchone()
                available_quantity = result[0] if result else 0
                assigned_quantity = result[1] if result else 0

            # Calculate if there is enough stock
            if quantity > available_quantity:
                return JsonResponse({'status': 'error', 'message': 'Quantity exceeds available stock.'})

            # Step 2: Update the equipment details if quantity is within limit
            with connection.cursor() as cursor:
                cursor.execute("""
                    UPDATE temp_equipment_details
                    SET equipment_name = %s, quantity = %s, equipment_unit_price = %s, equipment_total = %s, equipment_notes = %s
                    WHERE id = %s
                """, [equipment_name, quantity, unit_price, total, equipment_notes, row_equip_id])

            # Update the location and incharge
            with connection.cursor() as cursor:
                cursor.execute("""
                    UPDATE temp_equipment_details
                    SET location = %s, incharge = %s, equipment_setup_date = %s, equipment_rehearsal_date = %s
                    WHERE equipment_detail_id = %s
                """, [location, incharge, setup_date, rehearsal_date, element_equip_id])

            return JsonResponse({'status': 'success'})

        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)})

    else:
        return JsonResponse({'status': 'error', 'message': 'Invalid request method.'})



@csrf_exempt
def insert_equipment_details_id(request):
    print('Check the insert equipment details id is working..')
    if request.method == 'POST':
        print('Check the POST method')
        try:
            print('Check the try block')
            equipment_data = json.loads(request.body)
            print('Check the Equipment DATA:', equipment_data)

            with connection.cursor() as cursor:
                print('Check the cursor connection')
                for item in equipment_data:
                    print('Current item being processed:', item)

                    # Check for required fields
                    if 'equipment_name' not in item or 'equipment_detail_id' not in item:
                        return JsonResponse({'error': 'Required fields missing in one of the entries'}, status=400)
                    print('Current item being processed:', item)

                    # Convert data types
                    quantity = int(item['quantity'])
                    equipment_unit_price = float(item['equipment_unit_price'])
                    equipment_total = float(item['equipment_total'])

                    # Fetch the equipment_notes from the item
                    equipment_notes = item.get('equipment_notes', '')  # Default to empty string if not provided

                    # Check if the equipment_name already exists for the given equipment_detail_id
                    cursor.execute("""
                        SELECT COUNT(*)
                        FROM public.temp_equipment_details
                        WHERE equipment_name = %s AND equipment_detail_id = %s
                    """, [item['equipment_name'], item['equipment_detail_id']])

                    result = cursor.fetchone()
                    if result[0] > 0:
                        print(
                            f"Skipping insertion for equipment '{item['equipment_name']}' because it already exists for equipment_detail_id {item['equipment_detail_id']}")
                        continue  # Skip this item since it's already present

                    # Print the values to debug
                    print('Inserting values:', (
                        item['temp_id'],
                        item['equipment_detail_id'],
                        item['location'],
                        item['incharge'],
                        item['setup_date'],
                        item['rehearsal_date'],
                        item['equipment_name'],
                        quantity,
                        equipment_unit_price,
                        equipment_total,
                        equipment_notes  # Include equipment_notes here
                    ))

                    # Insert into the temp_equipment_details table
                    cursor.execute(""" 
                        INSERT INTO public.temp_equipment_details (
                            temp_id, equipment_detail_id, location, incharge, equipment_setup_date, equipment_rehearsal_date,
                            equipment_name, quantity, equipment_unit_price, equipment_total, equipment_notes
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        item['temp_id'],
                        item['equipment_detail_id'],
                        item['location'],
                        item['incharge'],
                        item['setup_date'],
                        item['rehearsal_date'],
                        item['equipment_name'],
                        quantity,
                        equipment_unit_price,
                        equipment_total,
                        equipment_notes  # Pass equipment_notes as a parameter
                    ))

                    print('Inserted item', item)

            return JsonResponse({'message': 'Data inserted successfully'}, status=200)

        except Exception as e:
            print(f"Error inserting data: {str(e)}")  # Print the error for debugging
            return JsonResponse({'error': str(e)}, status=500)

    return JsonResponse({'error': 'Invalid request method'}, status=400)



def save_crew_allocation(request):
    if request.method == 'POST':
        temp_id = request.POST.get('temp_id')
        crew_type = request.POST.get('crew_type')
        crew_no_of_days = request.POST.get('crew_no_of_days')
        perday_charges = request.POST.get('perday_charges')
        total = request.POST.get('total')
        crew_notes = request.POST.get('crew_notes')

        # Call the PostgreSQL function
        call_function_query = """
        SELECT * FROM insert_temp_crew_allocation(%s, %s, %s, %s, %s, %s);
        """

        with connection.cursor() as cursor:
            cursor.execute(call_function_query, [
                temp_id,
                crew_type,
                crew_no_of_days,
                perday_charges,
                total,
                crew_notes
            ])
            result = cursor.fetchone()

        if result:
            data = {
                'status': 'success',
                'crew_allocation_id': result[0],  # ID returned by the function
                'temp_id': result[1],
                'crew_type': result[2],
                'crew_no_of_days': result[3],
                'perday_charges': result[4],
                'total': result[5],
                'crew_notes': result[6]
            }
            return JsonResponse(data)
        else:
            return JsonResponse({'status': 'error', 'message': 'Crew allocation not found'}, status=404)

    return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=400)


@csrf_exempt
def delete_crew_allocation_row(request):
    if request.method == 'POST':
        crew_allocation_id = request.POST.get('crew_allocation_id')

        # Call the PostgreSQL function to delete the crew allocation
        with connection.cursor() as cursor:
            cursor.execute("SELECT manage_temp_crew_allocation(%s, %s);", ['delete', crew_allocation_id])

        return JsonResponse({'status': 'success'})

    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'})


@csrf_exempt
def update_crew_allocation_row(request):
    if request.method == 'POST':
        # Retrieve data from the request
        crew_allocation_id = request.POST.get('id')
        crew_type = request.POST.get('crew_type')
        no_of_days = request.POST.get('no_of_days')
        perday_charges = request.POST.get('perday_charges')
        total = request.POST.get('total')
        crew_notes = request.POST.get('crew_notes')

        try:
            # Call the PostgreSQL function to update the crew allocation
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT manage_temp_crew_allocation(%s, %s, %s, %s, %s, %s, %s);
                """, ['update', crew_allocation_id, crew_type, no_of_days, perday_charges, total, crew_notes])

            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})

    return JsonResponse({'success': False, 'error': 'Invalid request method.'})


def search_equipment(request):
    if request.method == 'GET':
        query = request.GET.get('query', '')
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    el.equipment_name,
                    COUNT(sd.barcode_no) AS total_quantity,
                    COUNT(CASE WHEN sd.scan_flag IS NULL OR sd.scan_flag = TRUE THEN 1 END) AS available_quantity
                FROM 
                    equipment_list el
                LEFT JOIN 
                    stock_details sd ON el.id = sd.equipment_id
                WHERE 
                    el.equipment_name ILIKE %s
                GROUP BY 
                    el.equipment_name
            """, [f'%{query}%'])

            rows = cursor.fetchall()
            equipment_data = [
                {
                    'equipment_name': row[0],
                    'total_quantity': row[1],
                    'available_quantity': row[2]
                }
                for row in rows
            ]

        return JsonResponse(equipment_data, safe=False)

def get_sub_categories(request):
    with connection.cursor() as cursor:
        # Call the PostgreSQL function to get active sub-categories with their category names
        cursor.execute("SELECT * FROM get_active_subcategories()")
        sub_categories = cursor.fetchall()

    # Prepare the data to be returned as JSON
    sub_category_list = []
    for sub in sub_categories:
        sub_category_list.append({
            "id": sub[0],
            "name": sub[1],
            "category_name": sub[2]
        })
        print('Fetch the DETAILS:', sub_category_list)

    return JsonResponse(sub_category_list, safe=False)

def fetch_all_subcategories(request):
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT id, name, type
            FROM public.sub_category
            WHERE status = true
        """)
        subcategories = cursor.fetchall()

    subcategory_list = []
    for subcategory in subcategories:
        subcategory_list.append({
            'id': subcategory[0],
            'name': subcategory[1],
            'type': subcategory[2],
        })

    return JsonResponse(subcategory_list, safe=False)


def fetch_equipment_with_barcodes(request):
    sub_category_id = request.GET.get('equipment_id')
    print('Fetch the sub_category ID:', sub_category_id)  # Debugging line

    # Validate that sub_category_id is present and is a valid integer
    if not sub_category_id or not sub_category_id.isdigit():
        return JsonResponse([], safe=False)  # Return an empty response if ID is invalid

    sub_category_id = int(sub_category_id)  # Convert to integer

    with connection.cursor() as cursor:
        # Retrieve all equipment IDs where sub_category_id matches
        cursor.execute('''
            SELECT id
            FROM equipment_list
            WHERE sub_category_id = %s
        ''', [sub_category_id])

        equipment_ids = cursor.fetchall()
        equipment_ids = [row[0] for row in equipment_ids]  # Extract IDs from the results
        print('Fetched equipment IDs:', equipment_ids)

        if not equipment_ids:
            return JsonResponse([], safe=False)  # Return empty if no equipment IDs are found

        # Get equipment IDs with available barcodes and their quantities
        cursor.execute('''
            SELECT e.id, e.equipment_name, COALESCE(COUNT(s.barcode_no), 0) AS available_quantity
            FROM equipment_list e
            LEFT JOIN stock_details s ON e.id = s.equipment_id 
                AND s.barcode_no IS NOT NULL
                AND (s.scan_flag IS NULL OR s.scan_flag = TRUE)
            WHERE e.id = ANY(%s)
            GROUP BY e.id
        ''', [equipment_ids])

        equipment_rows = cursor.fetchall()
        equipment_names = [
            {
                'equipment_id': row[0],
                'equipment_name': row[1],
                'available_quantity': row[2]
            }
            for row in equipment_rows
        ]

    return JsonResponse(equipment_names, safe=False)


def search_crew(request):
    search_query = request.GET.get('search', '')
    employees = []

    if search_query:
        with connection.cursor() as cursor:
            # Adjusted query to select only the first image per employee
            query = """
                SELECT e.id, e.employee_id, e.name, e.email, e.mobile_no, COALESCE(MIN(ei.images), '') AS image_path
                FROM public.employee e
                LEFT JOIN public.employee_images ei ON e.id = ei.employee_id
                WHERE 
                    e.name ILIKE %s OR 
                    e.email ILIKE %s OR
                    CAST(e.employee_id AS TEXT) ILIKE %s OR
                    CAST(e.mobile_no AS TEXT) ILIKE %s
                GROUP BY e.id
            """
            search_param = f"%{search_query}%"
            cursor.execute(query, [search_param, search_param, search_param, search_param])
            rows = cursor.fetchall()

            for row in rows:
                image_path = row[5]  # Adjust index as needed
                image_url = None
                if image_path:
                    try:
                        image_relative_path = os.path.relpath(image_path, settings.MEDIA_ROOT)
                        image_url = os.path.join(settings.MEDIA_URL, image_relative_path).replace('\\', '/')
                    except ValueError as ve:
                        logger.error("ValueError occurred while computing relative path: %s", str(ve))
                        image_url = os.path.join(settings.MEDIA_URL, 'profilepic/default.jpg')
                else:
                    image_url = os.path.join(settings.MEDIA_URL, 'profilepic/default.jpg')

                employees.append({
                    'id': row[0],
                    'employee_id': row[1],
                    'name': row[2],
                    'email': row[3],
                    'mobile_no': row[4],
                    'image_url': image_url,  # Include image URL
                })

    # Create the response data
    data = [
        {
            'id': employee['id'],
            'employee_id': employee['employee_id'],
            'name': employee['name'],
            'email': employee['email'],
            'mobile_no': employee['mobile_no'],
            'image_url': employee['image_url'],  # Include image URL
        }
        for employee in employees
    ]

    return JsonResponse(data, safe=False)


def subcategorytest_list(request):
    # Create a cursor object
    with connection.cursor() as cursor:
        # Call the PostgreSQL function
        cursor.execute("SELECT * FROM fetch_subcategories()")

        # Fetch all rows from the executed query
        rows = cursor.fetchall()
        print('Fetch the DATA:', rows)

        # Prepare the data to be sent as JSON
        subcategories = []
        for row in rows:
            subcategories.append({
                'id': row[0],
                'name': row[1],
                'category_name': row[2],
                'status': row[3],
                'created_by': row[4],
                'created_date': row[5].strftime('%d-%m-%Y') if row[5] else None
            })

        # Return the data as JSON
        return JsonResponse({'subcategories': subcategories})


def fetch_categories(request):
    with connection.cursor() as cursor:
        cursor.execute("SELECT category_id, category_name FROM public.master_category WHERE status = TRUE")
        categories = cursor.fetchall()

    # Convert query results to a list of dictionaries
    category_list = [{'category_id': row[0], 'category_name': row[1]} for row in categories]

    return JsonResponse({'categories': category_list})


@csrf_exempt
def add_subcategory(request):
    logger.info('Entering the add_subcategory function')

    if request.method == 'POST':
        try:
            # Parse JSON body
            data = json.loads(request.body)
            logger.info('Received data: %s', data)

            category_id = data.get('category_id')
            name = data.get('subcategory_name').upper() if data.get('subcategory_name') else None
            status = data.get('status')
            created_by = request.session.get('user_id') or 1  # Fetch user_id from session, fallback to 1 if missing
            created_date = timezone.now()  # Correct usage of timezone.now()

            # Validate required fields
            if not category_id or not name or status is None:
                logger.warning('Missing required fields')
                return JsonResponse({'success': False, 'message': 'Missing required fields.'})

            # Check if the subcategory already exists in the given category
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT COUNT(*) FROM public.sub_category
                    WHERE category_id = %s AND name = %s
                """, [category_id, name])

                subcategory_count = cursor.fetchone()[0]

            if subcategory_count > 0:
                logger.warning('Duplicate subcategory found')
                return JsonResponse({'success': False, 'message': 'Subcategory already exists.'})

            logger.info('Validated data: category_id=%s, name=%s, status=%s, created_by=%s, created_date=%s',
                        category_id, name, status, created_by, created_date)

            # Insert data into sub_category table
            with connection.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO public.sub_category (category_id, name, status, created_by, created_date)
                    VALUES (%s, %s, %s, %s, %s)
                """, [category_id, name, status, created_by, created_date])

            logger.info('Subcategory added successfully.')
            return JsonResponse({'success': True, 'message': 'Subcategory added successfully!'})

        except json.JSONDecodeError:
            logger.error('Invalid JSON data received', exc_info=True)
            return JsonResponse({'success': False, 'message': 'Invalid JSON data.'})
        except Exception as e:
            logger.error('An error occurred while adding subcategory: %s', str(e), exc_info=True)
            return JsonResponse({'success': False, 'message': str(e)})

    logger.warning('Invalid request method')
    return JsonResponse({'success': False, 'message': 'Invalid request method.'})


@csrf_exempt
def delete_subcategory(request, subcategory_id):
    if request.method == 'POST':
        try:
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM public.sub_category WHERE id = %s", [subcategory_id])
            return JsonResponse({'success': True, 'message': 'Subcategory deleted successfully!'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})
    return JsonResponse({'success': False, 'message': 'Invalid request method.'})


def delete_category(request, category_id):
    try:
        # Check if the request method is POST
        if request.method != 'POST':
            return JsonResponse({'success': False, 'message': 'Invalid request method.'}, status=400)

        with connection.cursor() as cursor:
            # Check if there are any associated rows in the sub_category table
            cursor.execute("""
                SELECT COUNT(*)
                FROM public.sub_category
                WHERE category_id = %s
            """, [category_id])

            count = cursor.fetchone()[0]

            if count > 0:
                return JsonResponse(
                    {'success': False, 'message': 'Cannot delete category because it is referenced in sub_category.'},
                    status=400)

            # Proceed to delete the category from the master_category table
            cursor.execute("""
                DELETE FROM public.master_category
                WHERE category_id = %s
            """, [category_id])

            return JsonResponse({'success': True, 'message': 'Category deleted successfully!'})

    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)


def update_master_category(request, category_id):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Invalid request method.'}, status=400)

    try:
        category_name = request.POST.get('category_name')
        if category_name:
            category_name = category_name.upper()  # Convert category_name to uppercase

        with connection.cursor() as cursor:
            # Correct SQL query
            cursor.execute("""
                UPDATE public.master_category
                SET category_name = %s
                WHERE category_id = %s
            """, [category_name, category_id])

            # Check if the update was successful
            if cursor.rowcount == 0:
                return JsonResponse({'success': False, 'message': 'No category found with the given ID.'}, status=404)

            return JsonResponse({'success': True, 'message': 'Category updated successfully!'})

    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)


def update_sub_category(request, subcategory_id):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Invalid request method.'}, status=400)

    try:
        # Retrieve and process the form data
        name = request.POST.get('name').upper()  # Convert the name to uppercase
        status = request.POST.get('status') == 'true'  # Convert string 'true'/'false' to boolean

        with connection.cursor() as cursor:
            # Call the PostgreSQL function to update the subcategory
            cursor.execute("""
                SELECT update_subcategory(%s, %s, %s)
            """, [subcategory_id, name, status])

            # Get the result of the function
            result = cursor.fetchone()[0]

            if not result:
                return JsonResponse({'success': False, 'message': 'No subcategory found with the given ID.'},
                                    status=404)

            return JsonResponse({'success': True, 'message': 'Subcategory updated successfully!'})

    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)


def get_sub_categories(request):
    with connection.cursor() as cursor:
        # Call the PostgreSQL function to get active sub-categories with their category names
        cursor.execute("SELECT * FROM get_active_subcategories()")
        sub_categories = cursor.fetchall()

    # Prepare the data to be returned as JSON
    sub_category_list = []
    for sub in sub_categories:
        sub_category_list.append({
            "id": sub[0],
            "name": sub[1],
            "category_name": sub[2]
        })
        print('Fetch the DETAILS:', sub_category_list)

    return JsonResponse(sub_category_list, safe=False)


@csrf_exempt
def submit_equipment(request):
    if request.method == 'POST':
        try:
            # Retrieve form data
            equipment_name = request.POST.get('equipmentName')
            equipment_SubCategory = request.POST.get('equipmentSubCategory')
            category_type = request.POST.get('equipmentCategory')
            dimension_h = request.POST.get('dimension_h')
            dimension_w = request.POST.get('dimension_w')
            dimension_l = request.POST.get('dimension_l')
            weight = request.POST.get('weight')
            volume = request.POST.get('volume')
            hsn_no = request.POST.get('hsn_no')  # Handle as a string, not an integer
            country_origin = request.POST.get('country_origin')

            # Retrieve `created_by` from session
            created_by = request.session.get('user_id')  # Assuming user_id is stored in the session

            if not created_by:
                return JsonResponse({'status': 'error', 'message': 'User not authenticated. Please log in.'},
                                    status=403)

            # Check if equipment name already exists
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT COUNT(*) FROM public.equipment_list WHERE equipment_name = %s
                """, [equipment_name])
                existing_count = cursor.fetchone()[0]

            if existing_count > 0:
                return JsonResponse(
                    {'status': 'error', 'message': 'Equipment name already exists. Please choose a different name.'},
                    status=400)

            # Handle file uploads to Cloudinary
            # Handle file uploads to Cloudinary
            image_urls = []
            for field_name in ['image1[]', 'image2[]', 'image3[]']:
                for image in request.FILES.getlist(field_name):
                    if image:
                        result = cloudinary.uploader.upload(image)
                        image_urls.append(result['secure_url'])
                        print(f"Uploaded {field_name} to Cloudinary: {result['secure_url']}")

            while len(image_urls) < 3:
                image_urls.append(None)

            # Log the image URLs to ensure they are captured correctly
            print("Image URLs to be inserted:", image_urls)

            # Ensure numeric fields are properly cast
            dimension_h = float(dimension_h) if dimension_h else None
            dimension_w = float(dimension_w) if dimension_w else None
            dimension_l = float(dimension_l) if dimension_l else None
            weight = float(weight) if weight else None
            volume = float(volume) if volume else None

            # Call the PostgreSQL function to insert equipment and attachments
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT insert_equipment_with_attachments(
                        %s::varchar, %s::varchar, %s::varchar, 
                        %s::numeric, %s::numeric, %s::numeric, 
                        %s::numeric, %s::numeric, %s::varchar, 
                        %s::varchar, %s::int, %s::varchar, 
                        %s::varchar, %s::varchar)
                """, [
                    equipment_name, equipment_SubCategory, category_type,
                    dimension_h, dimension_w, dimension_l,
                    weight, volume, hsn_no, country_origin,
                    created_by, image_urls[0], image_urls[1], image_urls[2]
                ])
                equipment_list_id = cursor.fetchone()[0]

            return JsonResponse({'status': 'success', 'equipment_id': equipment_list_id})

        except Exception as e:
            print("Error:", str(e))
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

    return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=400)


def fetch_equipment_list(request):
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT 
                e.id,
                e.equipment_name,
                s.name as subcategory_name,
                u.username as created_by,  -- Assuming you have a user table with username
                to_char(e.created_date, 'YYYY-MM-DD') as created_date,  -- Format the date
                a.image_1 as image_url  -- Assuming image_1 is the URL or path to the image
            FROM 
                equipment_list e
            JOIN 
                sub_category s ON e.sub_category_id = s.id
            JOIN 
                auth_user u ON e.created_by = u.id  -- Replace auth_user with your actual user table
            LEFT JOIN 
                equipment_list_attachments a ON e.id = a.equipment_list_id
            ORDER BY 
                e.created_date DESC;
        """)
        equipment_list = cursor.fetchall()

        # Structure the response
        equipment_list_dict = [
            {
                'id': row[0],
                'equipment_name': row[1],
                'subcategory_name': row[2],
                'created_by': row[3],
                'created_date': row[4],
                'image_url': row[5],
            }
            for row in equipment_list
        ]

    return JsonResponse({'equipment_list': equipment_list_dict})


@csrf_exempt
def delete_equipment(request, equipment_id):
    if request.method == 'POST':
        try:
            with connection.cursor() as cursor:
                # Call the PostgreSQL function to delete the equipment
                cursor.callproc('delete_equipment_func', [equipment_id])
                result = cursor.fetchone()[0]

            if 'successfully' in result:
                return JsonResponse({'success': True, 'message': result})
            else:
                return JsonResponse({'success': False, 'message': result})

        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})

    return JsonResponse({'success': False, 'message': 'Invalid request method'})


def fetch_equipment_details(request):
    equipment_id = request.GET.get('equipmentId')

    if not equipment_id:
        return JsonResponse({'error': 'No equipmentId provided'}, status=400)

    try:
        with connection.cursor() as cursor:
            # Fetch equipment details, including subcategory name and attachment details
            cursor.execute("""
                SELECT el.id, el.equipment_name, el.sub_category_id, sc.name as sub_category_name, el.category_type,
                       el.dimension_height, el.dimension_width, el.dimension_length, el.weight, el.volume,
                       el.hsn_no, el.country_origin, el.status, el.created_by, el.created_date,
                       ea.image_1, ea.image_2, ea.image_3,
                       sd.vender_name, sd.purchase_date, sd.unit_price, sd.rental_price, sd.reference_no,
                       sd.unit, sd.serial_no, sd.barcode_no, sd.attchment  -- Fetch `attchment` field
                FROM public.equipment_list el
                LEFT JOIN public.equipment_list_attachments ea ON el.id = ea.equipment_list_id
                LEFT JOIN public.stock_details sd ON el.id = sd.equipment_id
                LEFT JOIN public.sub_category sc ON el.sub_category_id = sc.id
                WHERE el.id = %s
            """, [equipment_id])
            row = cursor.fetchone()

            if not row:
                return JsonResponse({'error': 'Equipment not found'}, status=404)

            # Extract data from the row
            response_data = {
                'equipment': {
                    'id': row[0],
                    'equipment_name': row[1],
                    'sub_category_name': row[3],  # Subcategory name from JOIN
                    'category_type': row[4],
                    'dimension_height': row[5],
                    'dimension_width': row[6],
                    'dimension_length': row[7],
                    'weight': row[8],
                    'volume': row[9],
                    'hsn_no': row[10],
                    'country_origin': row[11],
                    'status': row[12],
                    'created_by': row[13],
                    'created_date': row[14],
                },
                'attachments': {
                    'image_1': row[15],
                    'image_2': row[16],
                    'image_3': row[17],
                },
                'stock_details': {
                    'vendor_name': row[18],
                    'purchase_date': row[19],
                    'unit_price': row[20],
                    'rental_price': row[21],
                    'reference_no': row[22],
                    'unit': row[23],
                    'serial_no': row[24],
                    'barcode_no': row[25],
                    'attachment': row[26].split('/')[-1] if row[26] else None,  # Extract filename or path
                }
            }
            print('FETCH THE DATA:', response_data)  # Debugging purpose
            return JsonResponse(response_data)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
def update_equipment(request):
    if request.method == 'POST':
        try:
            equipment_id = request.POST.get('equipmentId')
            if not equipment_id:
                return JsonResponse({'success': False, 'error': 'Equipment ID is required'})

            if 'equipmentName' in request.POST:
                return update_equipment_details(request, equipment_id)
            elif 'vendor_name' in request.POST:
                return update_stock_details(request, equipment_id)
            else:
                return JsonResponse({'success': False, 'error': 'Unknown update type'})

        except Exception as e:
            print("Error during equipment update:", str(e))
            return JsonResponse({'success': False, 'error': str(e)})

    return JsonResponse({'success': False, 'error': 'Invalid request method'})


@csrf_exempt
def update_equipment_details(request, equipment_id):
    try:
        # Ensure Cloudinary is configured
        cloudinary.config(
            cloud_name='dvemtlkjh',
            api_key='679749273824336',
            api_secret='t4LpyFrIjqUPJ2stsBvDwHbLcA0'
        )

        # Extract form data
        equipment_name = request.POST.get('equipmentName')
        sub_category_name = request.POST.get('subCategoryName')
        category_type = request.POST.get('categoryType')
        dimension_height = request.POST.get('dimension_h')
        dimension_width = request.POST.get('dimension_w')
        dimension_length = request.POST.get('dimension_l')
        weight = request.POST.get('weight')
        volume = request.POST.get('volume')
        hsn_no = request.POST.get('hsn_no')
        country_origin = request.POST.get('country_origin')

        # Fetch the sub_category_id from the sub_category table
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT id FROM public.sub_category WHERE name = %s
            """, [sub_category_name])
            sub_category_id = cursor.fetchone()

            if not sub_category_id:
                return JsonResponse({'success': False, 'error': 'Subcategory not found'})

            sub_category_id = sub_category_id[0]  # Get the integer ID

            # Handle file uploads independently
            image1 = request.FILES.get('image1[]')
            image2 = request.FILES.get('image2[]')
            image3 = request.FILES.get('image3[]')
            print("Files received:", request.FILES)

            # Fetch current attachments from the database
            cursor.execute("""
                SELECT image_1, image_2, image_3 FROM public.equipment_list_attachments WHERE equipment_list_id = %s
            """, [equipment_id])
            current_attachments = cursor.fetchone() or [None, None, None]
            image_urls = list(current_attachments)

            if image1:
                try:
                    result = cloudinary.uploader.upload(image1)
                    image_urls[0] = result.get('secure_url')
                except Exception as e:
                    return JsonResponse({'success': False, 'error': f"Error uploading Image 1: {str(e)}"})

            if image2:
                try:
                    result = cloudinary.uploader.upload(image2)
                    image_urls[1] = result.get('secure_url')
                except Exception as e:
                    return JsonResponse({'success': False, 'error': f"Error uploading Image 2: {str(e)}"})

            if image3:
                try:
                    result = cloudinary.uploader.upload(image3)
                    image_urls[2] = result.get('secure_url')
                except Exception as e:
                    return JsonResponse({'success': False, 'error': f"Error uploading Image 3: {str(e)}"})

            # Update the equipment_list table
            cursor.execute("""
                SELECT update_equipment_list_func(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, [
                equipment_id,
                equipment_name,
                sub_category_id,  # Correct ID being passed
                category_type,
                dimension_height,
                dimension_width,
                dimension_length,
                weight,
                volume,
                hsn_no,
                country_origin
            ])

            # Update `equipment_list_attachments` table
            cursor.execute("""
                UPDATE public.equipment_list_attachments
                SET image_1 = %s, image_2 = %s, image_3 = %s
                WHERE equipment_list_id = %s
            """, [image_urls[0], image_urls[1], image_urls[2], equipment_id])

        return JsonResponse({'success': True})

    except Exception as e:
        print("Error during equipment update:", str(e))
        return JsonResponse({'success': False, 'error': str(e)})

def update_stock_details(request, equipment_id):
    try:
        # Extract stock details data
        vendor_name = request.POST.get('vendor_name')
        purchase_date = request.POST.get('purchase_date')
        unit_price = request.POST.get('unit_price')
        rental_price = request.POST.get('rental_price')
        reference_no = request.POST.get('reference_no')
        quantity = request.POST.get('quantity')

        with connection.cursor() as cursor:
            # Update `stock_details` table
            cursor.execute("""
                SELECT update_stock_details_func(%s, %s, %s, %s, %s, %s, %s)
            """, [equipment_id, vendor_name, purchase_date, unit_price, rental_price, reference_no, quantity])

        return JsonResponse({'success': True})

    except Exception as e:
        print("Error during stock details update:", str(e))
        return JsonResponse({'success': False, 'error': str(e)})

@csrf_exempt
def insert_stock_details(request):
    if request.method == 'POST':
        try:
            equipment_id = request.POST.get('equipmentId')
            vendor_name = request.POST.get('edit_vendor_name')
            purchase_date = request.POST.get('purchase_date')
            unit_price = request.POST.get('unit_price')
            rental_price = request.POST.get('rental_price')
            reference_no = request.POST.get('reference_no')
            attachment = request.FILES.get('attachment')
            unit = request.POST.get('editUnit')

            # Initialize lists for serial numbers and barcode numbers
            serial_numbers = []
            barcode_numbers = []

            for key in request.POST:
                if key.startswith('serialNumber'):
                    serial_numbers.append(request.POST[key])
                if key.startswith('barcodeNumber'):
                    barcode_numbers.append(request.POST[key])

            attachment_path = None
            if attachment:
                attachment_path = f'media/uploads/{attachment.name}'
                with open(attachment_path, 'wb+') as destination:
                    for chunk in attachment.chunks():
                        destination.write(chunk)

            # Call the PostgreSQL function
            with connection.cursor() as cursor:
                cursor.callproc('insert_stock_details_func', [
                    equipment_id, vendor_name, purchase_date, unit_price, rental_price,
                    reference_no, attachment_path, unit, serial_numbers, barcode_numbers
                ])
                result = cursor.fetchone()[0]

            if 'successfully' in result:
                return JsonResponse({'success': True, 'message': result})
            else:
                return JsonResponse({'success': False, 'message': 'Error in processing stock details'})

        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)}, status=400)

    return JsonResponse({'success': False, 'message': 'Invalid request method'}, status=405)

def equipment_by_category(request):
    category_id = request.GET.get('category_id')

    if not category_id:
        return JsonResponse({'error': 'category_id is required'}, status=400)

    try:
        with connection.cursor() as cursor:
            # Use the above SQL query to fetch equipment by category
            cursor.execute("""
                SELECT e.id, e.equipment_name, e.category_type, e.dimension_height, e.dimension_width, 
                       e.dimension_length, e.weight, e.volume, e.hsn_no, e.country_origin,
                       e.status, e.created_by, e.created_date
                FROM equipment_list e
                JOIN sub_category s ON e.sub_category_id = s.id
                JOIN master_category m ON s.category_id = m.category_id
                WHERE m.category_id = %s;
            """, [category_id])
            equipment_list = cursor.fetchall()

        # Convert the result to a list of dictionaries
        equipment_data = [
            {
                'id': row[0],
                'equipment_name': row[1],
                'category_type': row[2],
                'dimension_height': row[3],
                'dimension_width': row[4],
                'dimension_length': row[5],
                'weight': row[6],
                'volume': row[7],
                'hsn_no': row[8],
                'country_origin': row[9],
                'status': row[10],
                'created_by': row[11],
                'created_date': row[12].strftime('%Y-%m-%d %H:%M:%S') if row[12] else None,
            }
            for row in equipment_list
        ]

        return JsonResponse({'equipment_list': equipment_data})

    except Exception as e:
        print(f"Error: {e}")
        return JsonResponse({'error': 'Internal Server Error'}, status=500)


def get_equipment_details(request, equipment_id):
    try:
        with connection.cursor() as cursor:
            # Fetch general equipment details including category_type (renamed to category_name)
            cursor.execute("""
                SELECT e.equipment_name, s.name as sub_category_name, e.category_type as category_name, e.weight,
                       e.dimension_length, e.dimension_width, e.dimension_height,
                       e.volume, e.hsn_no, e.country_origin, a.image_1, a.image_2, a.image_3,
                       COALESCE(MAX(sd.unit_price), 0) as unit_price, COALESCE(MAX(sd.rental_price), 0) as rental_price
                FROM equipment_list e
                JOIN sub_category s ON e.sub_category_id = s.id
                JOIN equipment_list_attachments a ON e.id = a.equipment_list_id
                LEFT JOIN stock_details sd ON e.id = sd.equipment_id
                WHERE e.id = %s
                GROUP BY e.equipment_name, s.name, e.category_type, e.weight,
                         e.dimension_length, e.dimension_width, e.dimension_height,
                         e.volume, e.hsn_no, e.country_origin, a.image_1, a.image_2, a.image_3
            """, [equipment_id])
            equipment = cursor.fetchone()

            print("Fetched Equipment Details:", equipment)  # Debugging print

            if not equipment:
                return JsonResponse({'error': 'Equipment not found'}, status=404)

            # Fetch total stock quantity (sum of units)
            cursor.execute("""
                SELECT COUNT(s.serial_no) FROM stock_details s WHERE s.equipment_id = %s AND scan_flag = FALSE
            """, [equipment_id])
            total_units = cursor.fetchone()[0]

            print("Total Units:", total_units)  # Debugging print

            # Correctly reference the image URLs from the fetched data
            equipment_details = {
                'equipment_name': equipment[0],
                'sub_category_name': equipment[1],
                'category_name': equipment[2],  # Use category_type as category_name
                'weight': equipment[3],
                'dimension_length': equipment[4],
                'dimension_width': equipment[5],
                'dimension_height': equipment[6],
                'volume': equipment[7],
                'hsn_no': equipment[8],
                'country_origin': equipment[9],
                'unit_price': equipment[13],  # Unit price
                'rental_price': equipment[14],  # Rental price
                'stock_qty': total_units if total_units else 0,  # Default to 0 if no stock
                'image_urls': [equipment[10], equipment[11], equipment[12]]  # Corrected image references
            }

            print("Final Equipment Details:", equipment_details)  # Debugging print

        return JsonResponse(equipment_details)
    except Exception as e:
        print("Error:", str(e))  # Debugging print
        return JsonResponse({'error': str(e)}, status=500)



def get_serial_details(request, equipment_id):
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT serial_no, barcode_no
            FROM stock_details
            WHERE equipment_id = %s
        """, [equipment_id])
        serial_details = cursor.fetchall()

    if serial_details:
        serial_data = [{'serial_no': sd[0], 'barcode_no': sd[1]} for sd in serial_details]
        return JsonResponse({'serial_details': serial_data})
    else:
        return JsonResponse({'serial_details': []})


def get_stock_details(request, equipment_id):
    try:
        with connection.cursor() as cursor:
            # Fetch stock summary
            logger.debug("Executing stock summary query for equipment_id: %s", equipment_id)
            cursor.execute("""
                SELECT s.vender_name, s.purchase_date, s.reference_no, COUNT(DISTINCT s.barcode_no) AS unique_barcode_count
                FROM stock_details s
                WHERE s.equipment_id = %s
                GROUP BY s.vender_name, s.purchase_date, s.reference_no
            """, [equipment_id])
            stock_summary = cursor.fetchall()

            if not stock_summary:
                logger.debug("No stock details found for equipment_id: %s", equipment_id)
                return JsonResponse({'message': 'No stock details available for this equipment.'}, status=404)

            stock_summary_list = [
                {
                    'vendor_name': row[0],
                    'purchase_date': row[1],
                    'reference_no': row[2],
                    'unique_barcode_count': row[3],
                }
                for row in stock_summary
            ]

            # Fetch detailed stock information
            logger.debug("Executing stock details query for equipment_id: %s", equipment_id)
            cursor.execute("""
                SELECT s.reference_no, s.barcode_no, s.serial_no
                FROM stock_details s
                WHERE s.equipment_id = %s
            """, [equipment_id])
            stock_details = cursor.fetchall()

            stock_details_list = [
                {
                    'reference_no': row[0],
                    'barcode_no': row[1],
                    'serial_no': row[2],
                }
                for row in stock_details
            ]

        logger.debug("Returning stock summary and details for equipment_id: %s", equipment_id)
        return JsonResponse({'stock_summary': stock_summary_list, 'stock_details': stock_details_list})
    except Exception as e:
        logger.error("Error fetching stock details for equipment_id: %s, error: %s", equipment_id, str(e))
        return JsonResponse({'error': str(e)}, status=500)


def get_categories(request):
    with connection.cursor() as cursor:
        # Fetch categories ordered by category_name in ascending order
        cursor.execute(
            "SELECT category_id, category_name FROM master_category WHERE status = TRUE ORDER BY category_name ASC")
        categories = cursor.fetchall()

    # Convert the result into a list of dictionaries
    category_list = [{'id': category[0], 'name': category[1]} for category in categories]

    # Determine the default category (first in alphabetical order)
    default_category = category_list[0] if category_list else None

    return JsonResponse({'categories': category_list, 'default_category': default_category})


def stock_details_view(request, equipment_id):
    print("stock_details_view called")
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM fetch_stock_details(%s)", [equipment_id])
        rows = cursor.fetchall()

        stock_details = [
            {
                "id": row[0],
                "serial_no": row[1],
                "barcode_no": row[2],
                "vendor_name": row[3],
                "unit_price": row[4],
                "rental_price": row[5],
                "purchase_date": row[6],
                "reference_no": row[7],
            }
            for row in rows
        ]

    return JsonResponse({'stock_details': stock_details})


@csrf_exempt
def update_stock_details(request):
    if request.method == 'POST':
        try:
            stock_id = request.POST.get('id')
            vender_name = request.POST.get('vender_name')
            purchase_date = request.POST.get('purchase_date') or None
            unit_price = request.POST.get('unit_price')
            rental_price = request.POST.get('rental_price')
            serial_no = request.POST.get('serial_no')
            barcode_no = request.POST.get('barcode_no')

            print(
                f"Received data: id={stock_id}, vender_name={vender_name}, purchase_date={purchase_date}, unit_price={unit_price}, rental_price={rental_price}, serial_no={serial_no}, barcode_no={barcode_no}")

            if not stock_id:
                return JsonResponse({'success': False, 'message': 'Stock ID is missing'})

            with connection.cursor() as cursor:
                cursor.execute("""
                    UPDATE stock_details
                    SET vender_name = %s,
                        purchase_date = %s,
                        unit_price = %s,
                        rental_price = %s,
                        serial_no = %s,
                        barcode_no = %s
                    WHERE id = %s
                """, [vender_name, purchase_date, unit_price, rental_price, serial_no, barcode_no, stock_id])

            return JsonResponse({'success': True, 'message': 'Stock details updated successfully.'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})

    return JsonResponse({'success': False, 'message': 'Invalid request method.'})


def fetch_job_list(request):
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT id, job_reference_no, title, status 
            FROM temp
        """)
        rows = cursor.fetchall()

        # Convert the result to a list of dictionaries
        jobs = []
        for row in rows:
            jobs.append({
                'id': row[0],
                'job_reference_no': row[1],
                'title': row[2],
                'status': row[3]
            })

    return JsonResponse(jobs, safe=False)


@csrf_exempt
def insert_equipment_details(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        equipment_details = data['equipmentDetails']

        with connection.cursor() as cursor:
            for detail in equipment_details:
                cursor.callproc('insert_equipment_details', [
                    detail['temp_id'],
                    detail['equipment_name'],
                    detail['quantity']
                ])

        return JsonResponse({'status': 'success'})
    return JsonResponse({'status': 'failed'}, status=400)


@csrf_exempt
def insert_sub_vendor_details(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)

            with connection.cursor() as cursor:
                cursor.callproc('insert_sub_vendor_details', [
                    data['temp_id'], data['vendor_name'],
                    data['sub_equipment_name'], data['sub_quantity']
                ])

            return JsonResponse({'status': 'success'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'error': str(e)})

    return JsonResponse({'status': 'error', 'error': 'Invalid request method'}, status=400)


@csrf_exempt
def insert_crew_allocation(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            temp_id = data['temp_id']
            employee_ids = data['employee_ids']

            # Convert employee_ids to a format suitable for PostgreSQL array
            employee_ids_str = '{' + ','.join(map(str, employee_ids)) + '}'

            with connection.cursor() as cursor:
                cursor.execute(
                    'SELECT insert_crew_allocation(%s, %s);',
                    [temp_id, employee_ids_str]
                )

            return JsonResponse({'status': 'success'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'error': str(e)})

    return JsonResponse({'status': 'error', 'error': 'Invalid request method'})


@csrf_exempt
def insert_transportation_data(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)

            with connection.cursor() as cursor:
                cursor.callproc('insert_transportation_data', [
                    data['temp_id'], data['driver_name'], data['contact_number'],
                    data['vehicle_number'], data['outside_driver_name'],
                    data['outside_contact_number'], data['outside_vehicle_number']
                ])

            return JsonResponse({'status': 'success'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'error': str(e)})

    return JsonResponse({'status': 'error', 'error': 'Invalid request method'})


def fetch_all_subcategories(request):
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT id, name
            FROM public.sub_category
            WHERE status = true
        """)
        subcategories = cursor.fetchall()

    subcategory_list = []
    for subcategory in subcategories:
        subcategory_list.append({
            'id': subcategory[0],
            'name': subcategory[1],
            # 'type': subcategory[2],
        })

    return JsonResponse(subcategory_list, safe=False)


def add_row(request):
    username = request.session.get('username')
    if request.method == 'POST':
        row_type = request.POST.get('type')
        cursor = connection.cursor()

        try:
            with transaction.atomic():
                created_by = request.session.get('user_id')
                created_date = datetime.now()

                if row_type == 'company':
                    company_name = request.POST.get('company_name')
                    gst_no = request.POST.get('gst_no')
                    pan_no = request.POST.get('pan_no')
                    company_email = request.POST.get('company_email')
                    office_address = request.POST.get('office_address')
                    billing_address = request.POST.get('billing_address')
                    country = request.POST.get('country')
                    state = request.POST.get('state')
                    city = request.POST.get('city')
                    post_code = request.POST.get('post_code')

                    if not all([company_name, gst_no, pan_no, company_email, office_address]):
                        return JsonResponse({'status': 'error', 'message': 'All fields are required'})

                    # Check for duplicate company name
                    cursor.execute("SELECT COUNT(*) FROM connects WHERE company_name = %s", [company_name])
                    if cursor.fetchone()[0] > 0:
                        return JsonResponse({'status': 'error', 'message': 'Company name already exists'})

                    query = "SELECT add_company(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
                    cursor.execute(query, (
                        row_type, company_name, gst_no, pan_no, company_email, office_address, billing_address, country,
                        state, city, post_code, created_by, created_date))

                elif row_type == 'venue':
                    venue_name = request.POST.get('venue_name')
                    venue_address = request.POST.get('venue_address')
                    venue_country = request.POST.get('venue_country')
                    venue_state = request.POST.get('venue_state')
                    venue_city = request.POST.get('venue_city')
                    venue_postcode = request.POST.get('venue_postcode')

                    if not all([venue_name, venue_address]):
                        return JsonResponse({'status': 'error', 'message': 'All fields are required'})

                    # Check for duplicate venue name
                    cursor.execute("SELECT COUNT(*) FROM connects WHERE venue_name = %s", [venue_name])
                    if cursor.fetchone()[0] > 0:
                        return JsonResponse({'status': 'error', 'message': 'Venue name already exists'})

                    query = "SELECT add_venue(%s, %s, %s, %s, %s, %s, %s, %s, %s)"
                    cursor.execute(query, (
                        row_type, venue_name, venue_address, venue_country, venue_state, venue_city, venue_postcode,
                        created_by, created_date))

                elif row_type == 'individual':
                    individual_name = request.POST.get('individual_name')
                    individual_mobile = request.POST.get('individual_mobile')
                    individual_social = request.POST.get('individual_social')
                    individual_email = request.POST.get('individual_email')
                    individual_company = request.POST.get('individual_company')
                    individual_address = request.POST.get('individual_address')
                    individual_country = request.POST.get('individual_country')
                    individual_state = request.POST.get('individual_state')
                    individual_city = request.POST.get('individual_city')
                    individual_postcode = request.POST.get('individual_postcode')

                    if not all([individual_name, individual_mobile, individual_email]):
                        return JsonResponse({'status': 'error', 'message': 'All fields are required'})

                    # Check for duplicate mobile number or email
                    cursor.execute("SELECT COUNT(*) FROM connects WHERE mobile_no = %s OR individual_email = %s",
                                   [individual_mobile, individual_email])
                    if cursor.fetchone()[0] > 0:
                        return JsonResponse({'status': 'error', 'message': 'Mobile number or email already exists'})

                    query = "SELECT add_individual(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
                    cursor.execute(query, (
                        row_type, individual_name, individual_mobile, individual_social, individual_email,
                        individual_company, individual_address, individual_country, individual_state, individual_city,
                        individual_postcode, created_by, created_date))

                else:
                    return JsonResponse({'status': 'error', 'message': 'Invalid type'})

            return JsonResponse(
                {'status': 'success', 'message': f'{row_type.capitalize()} added successfully', 'username': username})

        except DatabaseError as e:
            return JsonResponse({'status': 'error', 'message': f'Database error: {str(e)}'})

        finally:
            cursor.close()

    return JsonResponse({'status': 'error', 'message': 'Invalid request method'})



def fetch_company_data(request):
    if request.method == 'GET':
        cursor = connection.cursor()
        cursor.callproc('fetch_company_data')
        rows = cursor.fetchall()
        cursor.close()

        data = []
        for row in rows:
            data.append({
                'id': row[0],
                'company_name': row[1],
                'gst_no': row[2],
                'pan_no': row[3],
                'company_email': row[4],
                'office_address': row[5],
                'billing_address': row[6],
                'country': row[7],
                'state': row[8],
                'city': row[9],
                'post_code': row[10],
            })

        return JsonResponse(data, safe=False)
    return JsonResponse({'error': 'Invalid request method'}, status=405)


def fetch_venue_data(request):
    if request.method == 'GET':
        cursor = connection.cursor()
        cursor.callproc('fetch_venue_data')
        rows = cursor.fetchall()
        cursor.close()

        data = []
        for row in rows:
            data.append({
                'id': row[0],
                'venue_name': row[1],
                'venue_address': row[2],
                'country': row[3],
                'state': row[4],
                'city': row[5],
                'post_code': row[6],
            })

        return JsonResponse(data, safe=False)
    return JsonResponse({'error': 'Invalid request method'}, status=405)


@csrf_exempt
def fetch_company_names(request):
    if request.method == 'GET':
        try:
            with connection.cursor() as cursor:
                # Execute SQL to fetch company names
                cursor.execute('SELECT id, company_name FROM public.connects WHERE type = %s', ['company'])
                rows = cursor.fetchall()

                # Convert fetched data to a list of dictionaries
                companies = [{'id': row[0], 'company_name': row[1]} for row in rows]
                print('Fetch the company_name:', companies)

            return JsonResponse(companies, safe=False)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)

    return JsonResponse({'error': 'Invalid request method'}, status=400)


def fetch_individual_data(request):
    if request.method == 'GET':
        cursor = connection.cursor()
        cursor.callproc('fetch_individual_data')
        rows = cursor.fetchall()
        cursor.close()

        data = []
        for row in rows:
            data.append({
                'id': row[0],
                'individual_name': row[1],
                'mobile_no': row[2],
                'social_no': row[3],
                'individual_email': row[4],
                'company': row[5],
                'individual_address': row[6],
                'country': row[7],
                'state': row[8],
                'city': row[9],
                'post_code': row[10],
            })

        return JsonResponse(data, safe=False)
    return JsonResponse({'error': 'Invalid request method'}, status=405)


@csrf_exempt
def delete_data(request):
    if request.method == 'POST':
        item_id = request.POST.get('id')

        try:
            with connection.cursor() as cursor:
                cursor.execute('DELETE FROM public.connects WHERE id = %s', [item_id])
            return JsonResponse({'status': 'success'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

    return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=400)


@csrf_exempt
def update_company_data(request):
    if request.method == 'POST':
        data = request.POST
        id = data.get('id')
        company_name = data.get('company_name')
        gst_no = data.get('gst_no')
        pan_no = data.get('pan_no')
        company_email = data.get('company_email')
        office_address = data.get('office_address')
        billing_address = data.get('billing_address')
        country = data.get('country')
        state = data.get('state')
        city = data.get('city')
        post_code = data.get('post_code')

        with connection.cursor() as cursor:
            cursor.callproc('update_company_data_func', [
                id, company_name, gst_no, pan_no, company_email,
                office_address, billing_address, country, state, city, post_code
            ])

        return JsonResponse({'status': 'success'})
    return JsonResponse({'status': 'error'}, status=400)


@csrf_exempt
def update_individual_data(request):
    if request.method == 'POST':
        id = request.POST.get('id')
        individual_name = request.POST.get('individual_name')
        mobile_no = request.POST.get('mobile_no')
        social_no = request.POST.get('social_no')
        individual_email = request.POST.get('individual_email')
        company = request.POST.get('company')
        individual_address = request.POST.get('individual_address')
        country = request.POST.get('country')
        state = request.POST.get('state')
        city = request.POST.get('city')
        post_code = request.POST.get('post_code')

        with connection.cursor() as cursor:
            cursor.callproc('update_individual_data_func', [
                id, individual_name, mobile_no, social_no, individual_email,
                company, individual_address, country, state, city, post_code
            ])

        return JsonResponse({'status': 'success'})
    return JsonResponse({'status': 'error', 'message': 'Invalid request method'})


@csrf_exempt
def update_venue_data(request):
    if request.method == 'POST':
        id = request.POST.get('id')
        venue_name = request.POST.get('venue_name')
        venue_address = request.POST.get('venue_address')
        country = request.POST.get('country')
        state = request.POST.get('state')
        city = request.POST.get('city')
        post_code = request.POST.get('post_code')

        with connection.cursor() as cursor:
            cursor.callproc('update_venue_data_func', [
                id, venue_name, venue_address, country, state, city, post_code
            ])

        return JsonResponse({'status': 'success'})
    return JsonResponse({'status': 'error', 'message': 'Invalid request method'})


def fetch_venue_address(request):
    print('Inside the venue address')
    venue_name = request.GET.get('venue_name', '').strip()
    if not venue_name:
        return JsonResponse({'venue_address': ''})  # Return empty if no venue name is provided

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT venue_address
            FROM public.connects
            WHERE venue_name = %s
            LIMIT 1
            """, [venue_name]
        )
        result = cursor.fetchone()
        venue_address = result[0] if result else ''

    return JsonResponse({'venue_address': venue_address})


def fetch_client_name(request):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT DISTINCT type, individual_name, company_name FROM public.connects"
        )
        client_names = []
        for row in cursor.fetchall():
            client_type, name, company_name = row
            if name:
                client_names.append({'type': client_type, 'name': name})
            if company_name:
                client_names.append({'type': client_type, 'name': company_name})

    return JsonResponse({'client_names': client_names})


def fetch_individual_names(request):
    client_name = request.GET.get('client_name')
    print('Fetch the client_name:', client_name)

    with connection.cursor() as cursor:
        print('Check the cursor object is working..')
        query = """
            SELECT individual_name, mobile_no 
            FROM public.connects 
            WHERE company = %s OR individual_name = %s
        """
        params = [client_name, client_name]
        print('Executing query:', query)
        print('With parameters:', params)

        try:
            cursor.execute(query, params)
            # Collect data into a list of dictionaries
            individual_names = [{'name': row[0], 'mobile': row[1]} for row in cursor.fetchall()]
            print('Fetch DATA:', individual_names)
        except Exception as e:
            print('Error executing query:', e)
            individual_names = []

    return JsonResponse({'individual_names': individual_names})


def get_employee_name(request):
    if request.method == 'GET':
        with connection.cursor() as cursor:
            cursor.execute("SELECT DISTINCT id, name FROM employee")
            employee_names = cursor.fetchall()
            print('Fetch employee names:', employee_names)
            employee_names_list = [{'id': row[0], 'name': row[1]} for row in employee_names]
            print('Fetch employee Names with id:', employee_names_list)
        return JsonResponse({'employee_names': employee_names_list})


@csrf_exempt
def insert_temp_data(request):
    username = request.session.get('username')
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            print('Fetch Form Extracted DATA:', data)

            created_by = request.session.get('user_id')  # Adjust as needed, or fetch from request
            created_date = datetime.now()  # Use the current timestamp

            # Convert the crew_type and employee lists to strings (or handle as needed)
            employee_str = ','.join(data['employee'])

            with connection.cursor() as cursor:
                cursor.callproc('insert_temp_data', [
                    data['title'], data['client_name'], data['contact_person_name'],
                    data['contact_person_number'], data['status'], data['venue_name'],
                    data['venue_address'], data['input_notes'], data['crew_type'], employee_str,
                    data['setup_date'], data['rehearsal_date'], data['event_date'],
                    data['dismantle_date'], data['total_days'], data['amount_row'],
                    data['discount'], data['amount_after_discount'], data['total_amount'],
                    created_by, created_date
                ])
                temp_id = cursor.fetchone()[0]

            return JsonResponse(
                {'status': 'success', 'temp_id': temp_id, 'username': username})
        except Exception as e:
            logger.error(f"Error inserting temp data: {e}")
            return JsonResponse({'status': 'failed', 'error': str(e)}, status=500)

    return JsonResponse({'status': 'failed'}, status=400)


@csrf_exempt
def insert_equipment_details(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        equipment_details = data['equipmentDetails']

        with connection.cursor() as cursor:
            for detail in equipment_details:
                cursor.callproc('insert_equipment_details', [
                    detail['temp_id'],
                    detail['equipment_name'],
                    detail['quantity']
                ])

        return JsonResponse({'status': 'success'})
    return JsonResponse({'status': 'failed'}, status=400)


def search_equipment(request):
    if request.method == 'GET':
        query = request.GET.get('query', '')
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    el.equipment_name,
                    COUNT(sd.barcode_no) AS total_quantity,
                    COUNT(CASE WHEN sd.scan_flag IS NULL OR sd.scan_flag = TRUE THEN 1 END) AS available_quantity
                FROM 
                    equipment_list el
                LEFT JOIN 
                    stock_details sd ON el.id = sd.equipment_id
                WHERE 
                    el.equipment_name ILIKE %s
                GROUP BY 
                    el.equipment_name
            """, [f'%{query}%'])

            rows = cursor.fetchall()
            equipment_data = [
                {
                    'equipment_name': row[0],
                    'total_quantity': row[1],
                    'available_quantity': row[2]
                }
                for row in rows
            ]

        return JsonResponse(equipment_data, safe=False)


def fetch_all_subcategories(request):
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT id, name
            FROM public.sub_category
            WHERE status = true
        """)
        subcategories = cursor.fetchall()

    subcategory_list = []
    for subcategory in subcategories:
        subcategory_list.append({
            'id': subcategory[0],
            'name': subcategory[1],
            # 'type': subcategory[2],
        })

    return JsonResponse(subcategory_list, safe=False)


def fetch_equipment_with_barcodes(request):
    sub_category_id = request.GET.get('equipment_id')
    print('Fetch the sub_category ID:', sub_category_id)  # Debugging line

    # Validate that sub_category_id is present and is a valid integer
    if not sub_category_id or not sub_category_id.isdigit():
        return JsonResponse([], safe=False)  # Return an empty response if ID is invalid

    sub_category_id = int(sub_category_id)  # Convert to integer

    with connection.cursor() as cursor:
        # Retrieve all equipment IDs where sub_category_id matches
        cursor.execute('''
            SELECT id
            FROM equipment_list
            WHERE sub_category_id = %s
        ''', [sub_category_id])

        equipment_ids = cursor.fetchall()
        equipment_ids = [row[0] for row in equipment_ids]  # Extract IDs from the results
        print('Fetched equipment IDs:', equipment_ids)

        if not equipment_ids:
            return JsonResponse([], safe=False)  # Return empty if no equipment IDs are found

        # Get equipment IDs with available barcodes and their quantities
        cursor.execute('''
            SELECT e.id, e.equipment_name, COALESCE(COUNT(s.barcode_no), 0) AS available_quantity
            FROM equipment_list e
            LEFT JOIN stock_details s ON e.id = s.equipment_id 
                AND s.barcode_no IS NOT NULL
                AND (s.scan_flag IS NULL OR s.scan_flag = TRUE)
            WHERE e.id = ANY(%s)
            GROUP BY e.id
        ''', [equipment_ids])

        equipment_rows = cursor.fetchall()
        equipment_names = [
            {
                'equipment_id': row[0],
                'equipment_name': row[1],
                'available_quantity': row[2]
            }
            for row in equipment_rows
        ]

    return JsonResponse(equipment_names, safe=False)


@csrf_exempt
def insert_sub_vendor_details(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)

            with connection.cursor() as cursor:
                cursor.callproc('insert_sub_vendor_details', [
                    data['temp_id'], data['vendor_name'],
                    data['sub_equipment_name'], data['sub_quantity']
                ])

            return JsonResponse({'status': 'success'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'error': str(e)})

    return JsonResponse({'status': 'error', 'error': 'Invalid request method'}, status=400)


def search_employee(request):
    search_text = request.GET.get('term', '')  # Get the search text from the request
    results = []

    if search_text:
        with connection.cursor() as cursor:
            query = """
            SELECT id, name 
            FROM employee 
            WHERE name ILIKE %s
            LIMIT 10  -- Add a limit to prevent returning too many results
            """
            cursor.execute(query, [f'%{search_text}%'])
            rows = cursor.fetchall()

            # Debugging print for verifying the fetched rows
            print(f'Search term: {search_text}, Rows fetched: {rows}')

            results = [{'id': row[0], 'name': row[1]} for row in rows]

    # If no results, optionally add a message
    if not results:
        print('No employees found for search:', search_text)

    return JsonResponse(results, safe=False)


@csrf_exempt
def fetch_crew_allocation(request):
    if request.method == 'GET':
        job_id = request.GET.get('jobId')
        print('Received job ID:', job_id)

        if not job_id:
            return JsonResponse({'error': 'Job ID is required'}, status=400)

        with connection.cursor() as cursor:
            print('Fetching crew allocation details from database')
            # Query to fetch crew allocation and employee details based on job_id (temp_id)
            cursor.execute("""
                SELECT 
                    tca.id, 
                    tca.crew_type, 
                    e.name AS employee_name
                FROM 
                    public.temp_crew_allocation tca
                JOIN 
                    public.employee e ON tca.employee_id = e.id
                WHERE 
                    tca.temp_id = %s
            """, [job_id])
            rows = cursor.fetchall()
            print('Crew allocation details:', rows)

        # Prepare the response data
        if rows:
            crew_data = [{
                'id': row[0],  # temp_crew_allocation id
                'crew_type': row[1],  # Crew type from temp_crew_allocation
                'employee_name': row[2],  # Employee name from employee table
            } for row in rows]

            # Return the fetched crew allocation data
            return JsonResponse({'data': crew_data}, status=200)
        else:
            # Return an empty data array if no records are found
            return JsonResponse({'data': [], 'message': 'No crew allocation found for this job'}, status=200)

    return JsonResponse({'error': 'Invalid request method'}, status=405)


@csrf_exempt
def insert_crew_allocation(request):
    if request.method == 'POST':
        temp_id = request.POST.get('temp_id')
        crew_type = request.POST.get('crew_type')
        employee_id = request.POST.get('employee_id')

        with connection.cursor() as cursor:
            # Insert the new crew allocation
            cursor.execute("""
                INSERT INTO temp_crew_allocation (temp_id, crew_type, employee_id)
                VALUES (%s, %s, %s)
                RETURNING id, crew_type, employee_id;
            """, [temp_id, crew_type, employee_id])

            # Fetch the newly inserted record
            new_record = cursor.fetchone()

        if new_record:
            # Return the new record in the JSON response
            return JsonResponse({
                'success': True,
                'id': new_record[0],
                'crew_type': new_record[1],
                'employee_id': new_record[2]
            })
        else:
            return JsonResponse({'success': False})


@csrf_exempt
def delete_crew_allocation(request):
    if request.method == 'POST':
        id = request.POST.get('id')

        with connection.cursor() as cursor:
            # Delete the record from temp_crew_allocation
            cursor.execute("""
                DELETE FROM temp_crew_allocation
                WHERE id = %s
            """, [id])

        return JsonResponse({'success': True})
    return JsonResponse({'success': False})


@csrf_exempt
def insert_transportation(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        temp_id = data.get('temp_id')
        driver_name = data.get('driver_name', '')
        contact_number = data.get('contact_number', '')
        vehicle_number = data.get('vehicle_number', '')
        outside_driver_name = data.get('outside_driver_name', '')
        outside_contact_number = data.get('outside_contact_number', '')
        outside_vehicle_number = data.get('outside_vehicle_number', '')

        # Insert into temp_transportation_allocation table
        with connection.cursor() as cursor:
            cursor.execute("""
                INSERT INTO public.temp_transportation_allocation
                (temp_id, driver_name, contact_number, vehicle_number, outside_driver_name, outside_contact_number, outside_vehicle_number)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, [temp_id, driver_name, contact_number, vehicle_number, outside_driver_name, outside_contact_number,
                  outside_vehicle_number])

        return JsonResponse({'status': 'success'})

    return JsonResponse({'status': 'error', 'message': 'Invalid request'}, status=400)


def get_temp_details(request, jobId):
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT * FROM public.temp
                WHERE id = %s
            """, [jobId])

            row = cursor.fetchone()
            print('Fetch the DATA:', row)

            if row:
                columns = [col[0] for col in cursor.description]
                data = dict(zip(columns, row))
                print('Fetch the DATA of ROW:', data)

                return JsonResponse(data)
            else:
                return JsonResponse({'error': 'No data found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def update_temp_details(request, jobId):
    if request.method == 'POST':
        employee_name = request.POST.getlist('employee_name')  # Get the crew_type as a list
        employee_name_array_literal = '{' + ','.join(employee_name) + '}'  # Convert to array literal format

        with connection.cursor() as cursor:
            cursor.callproc('update_temp_details_fn', [
                jobId,
                request.POST.get('title'),
                request.POST.get('client_name'),
                request.POST.get('contact_person_name'),
                request.POST.get('contact_person_number'),
                request.POST.get('status'),
                request.POST.get('crew_quantity'),
                employee_name_array_literal,  # Pass the array literal
                request.POST.get('venue_name'),
                request.POST.get('venue_address'),
                request.POST.get('input_notes'),
                request.POST.get('setup_date'),
                request.POST.get('rehearsal_date'),
                request.POST.get('event_date'),
                request.POST.get('dismantle_date'),
                request.POST.get('total_days'),
                request.POST.get('amount_row'),
                request.POST.get('discount'),
                request.POST.get('amount_after_discount'),
                request.POST.get('total_amount')
            ])
        return JsonResponse({'success': True})
    else:
        return JsonResponse({'error': 'Invalid request method'}, status=400)


def calculate_total_amount(request, job_id):
    print('Check the JOB ID:', job_id)
    with connection.cursor() as cursor:
        print('Working Cursor object')
        # Step 1: Fetch equipment and quantity from temp_equipment_details
        cursor.execute("""
            SELECT ted.equipment_name, ted.quantity
            FROM temp_equipment_details ted
            JOIN temp t ON t.id = ted.temp_id
            WHERE t.id = %s
        """, [job_id])
        equipment_data = cursor.fetchall()
        print('Fetch Details of equipment data:', equipment_data)

        total_amount = 0
        print('Total amount of equipment DATA:', total_amount)

        for equipment_name, quantity in equipment_data:
            print('Check the for in condition work')
            # Step 2: Get equipment ID from equipment_list
            cursor.execute("""
                SELECT id FROM equipment_list WHERE equipment_name = %s
            """, [equipment_name])
            equipment_id = cursor.fetchone()
            print('Check the equipment:', equipment_id)

            if equipment_id:
                equipment_id = equipment_id[0]

                # Step 3: Fetch rental price from stock_details
                cursor.execute("""
                    SELECT rental_price FROM stock_details WHERE equipment_id = %s
                """, [equipment_id])
                rental_price = cursor.fetchone()
                print('Details of rental Price:', rental_price)

                if rental_price:
                    rental_price = rental_price[0]

                    # Step 4: Calculate the total amount
                    total_amount += float(quantity) * float(rental_price)
                    print('total Amount:', total_amount)

        return JsonResponse({'total_amount': total_amount})


def fetch_edit_equipment_details(request, job_id):
    with connection.cursor() as cursor:
        cursor.callproc('fetch_edit_equipment_details', [job_id])
        equipment_details = cursor.fetchall()

    data = [
        {
            'id': row[0],
            'temp_id': row[1],
            'equipment_name': row[2],
            'quantity': row[3]
        } for row in equipment_details
    ]

    return JsonResponse(data, safe=False)


@csrf_exempt
def update_equipment_quantity(request):
    if request.method == 'POST':
        equipment_id = request.POST.get('id')
        new_quantity = request.POST.get('quantity')

        with connection.cursor() as cursor:
            cursor.callproc('update_equipment_quantity_fn', [equipment_id, new_quantity])

        return JsonResponse({'success': True})

    return JsonResponse({'error': 'Invalid request method'}, status=405)


def fetch_sub_vendor_details(request, job_id):
    with connection.cursor() as cursor:
        cursor.callproc('fetch_sub_vendor_details', [job_id])
        sub_vendor_details = cursor.fetchall()

    data = [
        {
            'id': row[0],
            'vendor_name': row[1],
            'sub_equipment_name': row[2],
            'sub_quantity': row[3]
        } for row in sub_vendor_details
    ]

    return JsonResponse(data, safe=False)


@csrf_exempt
def update_sub_vendor_details(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            id = data.get('id')
            vendor_name = data.get('vendor_name')
            equipment_name = data.get('equipment_name')
            quantity = data.get('quantity')

            if not all([id, vendor_name, equipment_name, quantity]):
                return JsonResponse({'status': 'failed', 'error': 'Missing required fields'}, status=400)

            with connection.cursor() as cursor:
                cursor.callproc('update_sub_vendor_details_fn', [id, vendor_name, equipment_name, quantity])

            return JsonResponse({'status': 'success'})
        except Exception as e:
            return JsonResponse({'status': 'failed', 'error': str(e)}, status=500)

    return JsonResponse({'status': 'failed', 'error': 'Invalid request method'}, status=400)


def delete_sub_vendor(request, id):
    try:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM temp_sub_vendor WHERE id = %s", [id])

        return JsonResponse({'success': True})

    except Exception as e:
        print(f"Error deleting sub-vendor: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
def fetch_crew_allocation(request):
    if request.method == 'GET':
        job_id = request.GET.get('jobId')
        print('Fetch the ID:', job_id)
        if not job_id:
            return JsonResponse({'error': 'Job ID is required'}, status=400)

        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT ca.id, ca.crew_type, e.name AS employee_name
                FROM public.temp_crew_allocation ca
                JOIN public.employee e ON ca.employee_id = e.id
                WHERE ca.temp_id = %s
            """, [job_id])
            rows = cursor.fetchall()
            print('Fetch the crew details:', rows)

        crew_data = []
        print('Fetch the crew allocation:', crew_data)
        for row in rows:
            crew_data.append({
                'id': row[0],
                'crew_type': row[1],
                'employee_name': row[2]
            })
            print('Fetch the correct details:', row)

        return JsonResponse({'data': crew_data})

    return JsonResponse({'error': 'Invalid request method'}, status=405)

def fetch_temp_crew_details(request):
    temp_id = request.GET.get('tempId')  # Get the temp_id from the AJAX request

    # Query the database using temp_id
    with connection.cursor() as cursor:
        query = """
            SELECT id, crew_type, emp_id, crew_no_of_days, perday_charges, total, crew_notes
            FROM temp_crew_allocation
            WHERE temp_id = %s
        """
        cursor.execute(query, [temp_id])
        crew_details = cursor.fetchall()

    # Prepare the response data
    data = []
    for row in crew_details:
        data.append({
            'id': row[0],
            'crew_type': row[1],
            'emp_id': row[2],
            'crew_no_of_days': row[3],
            'perday_charges': row[4],
            'total': row[5],
            'crew_notes': row[6],
        })

    # Return the data as a JSON response
    return JsonResponse({'status': 'success', 'data': data})


@csrf_exempt
def delete_crew_allocation(request, id):
    if request.method == 'DELETE':
        with connection.cursor() as cursor:
            cursor.execute("""
                DELETE FROM public.temp_crew_allocation
                WHERE id = %s
            """, [id])

            # Check if any row was deleted
            if cursor.rowcount > 0:
                return JsonResponse({'success': True})
            else:
                return JsonResponse({'error': 'No row found to delete'}, status=404)

    return JsonResponse({'error': 'Invalid request method'}, status=405)


def get_transportation_allocation(request):
    job_id = request.GET.get('jobId')
    if not job_id:
        return JsonResponse({'error': 'jobId is required'}, status=400)

    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT
                id,
                driver_name,
                contact_number,
                vehicle_number,
                outside_driver_name,
                outside_contact_number,
                outside_vehicle_number
            FROM
                public.temp_transportation_allocation
            WHERE
                temp_id = %s
        """, [job_id])
        rows = cursor.fetchall()

    result = []
    for row in rows:
        result.append({
            'id': row[0],
            'driver_name': row[1],
            'contact_number': row[2],
            'vehicle_number': row[3],
            'outside_driver_name': row[4],
            'outside_contact_number': row[5],
            'outside_vehicle_number': row[6],
        })

    return JsonResponse(result, safe=False)


@csrf_exempt
def delete_transportation_allocation(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        job_id = data.get('id')
        if not job_id:
            return JsonResponse({'error': 'ID is required'}, status=400)

        with connection.cursor() as cursor:
            cursor.execute("""
                DELETE FROM public.temp_transportation_allocation
                WHERE id = %s
            """, [job_id])

        return JsonResponse({'success': True})

    return JsonResponse({'error': 'Invalid request method'}, status=405)


def update_transportation_allocation(request):
    try:
        data = json.loads(request.body)
        row_id = data.get('id')
        driver_name = data.get('driver_name')
        contact_number = data.get('contact_number')
        vehicle_number = data.get('vehicle_number')
        outside_driver_name = data.get('outside_driver_name')
        outside_contact_number = data.get('outside_contact_number')
        outside_vehicle_number = data.get('outside_vehicle_number')

        # Update the row in the table using raw SQL
        with connection.cursor() as cursor:
            cursor.execute("""
                UPDATE public.temp_transportation_allocation
                SET driver_name = %s,
                    contact_number = %s,
                    vehicle_number = %s,
                    outside_driver_name = %s,
                    outside_contact_number = %s,
                    outside_vehicle_number = %s
                WHERE id = %s
            """, [
                driver_name,
                contact_number,
                vehicle_number,
                outside_driver_name,
                outside_contact_number,
                outside_vehicle_number,
                row_id
            ])

        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@csrf_exempt
def insert_transportation(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        temp_id = data.get('temp_id')
        driver_name = data.get('driver_name', '')
        contact_number = data.get('contact_number', '')
        vehicle_number = data.get('vehicle_number', '')
        outside_driver_name = data.get('outside_driver_name', '')
        outside_contact_number = data.get('outside_contact_number', '')
        outside_vehicle_number = data.get('outside_vehicle_number', '')

        # Insert into temp_transportation_allocation table
        with connection.cursor() as cursor:
            cursor.execute("""
                INSERT INTO public.temp_transportation_allocation
                (temp_id, driver_name, contact_number, vehicle_number, outside_driver_name, outside_contact_number, outside_vehicle_number)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, [temp_id, driver_name, contact_number, vehicle_number, outside_driver_name, outside_contact_number,
                  outside_vehicle_number])

        return JsonResponse({'status': 'success'})

    return JsonResponse({'status': 'error', 'message': 'Invalid request'}, status=400)


def edit_job(request, jobId):
    username = request.session.get('username')

    job_details = None

    if jobId:
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM temp WHERE id = %s", [jobId])
            job_details = cursor.fetchone()

    context = {
        'job': job_details,
        'username':username
    }
    return render(request, 'product_tracking/edit-job.html', context)


def update_total_amount_details(request, job_id):
    if request.method == 'POST':
        amount_row = request.POST.get('amount_row')
        discount = request.POST.get('discount')
        discounted_amount = request.POST.get('discounted_amount')
        total_amount = request.POST.get('total_amount')

        with connection.cursor() as cursor:
            cursor.execute("SELECT update_total_amount_details(%s, %s, %s, %s, %s)",
                           [job_id, amount_row, discount, discounted_amount, total_amount])

        return JsonResponse({'status': 'success', 'message': 'Details updated successfully'})
    else:
        return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=405)


@csrf_exempt
def print_jobs(request):
    job_id = request.GET.get('jobId')
    print('Fetch the jobId in print jobs:', job_id)

    if not job_id:
        return JsonResponse({'error': 'Job ID is required'}, status=400)

    # Query to fetch job details from the `temp` table
    job_query = '''
        SELECT id, job_reference_no, title, client_name, contact_person_name, contact_person_number,
               status, venue_name, venue_address, notes, crew_type, employee, setup_date, rehearsal_date,
               event_date, dismantle_date, total_days, amount_row, discount, amount_after_discount,
               total_amount, created_by, created_date
        FROM temp
        WHERE id = %s
    '''
    print('Fetch the job Query:', job_query)

    # Updated query to fetch the first row of each equipment_id including rental_price as integer
    # Simplified query to fetch only equipment names based on temp_id
    equipment_query = '''
        SELECT
            te.equipment_name,
            te.quantity,
            el.id AS equipment_id,
            el.category_type,
            el.sub_category_id,
            sc.name AS sub_category_name,
            sd.rental_price,
            te.equipment_notes,
            te.equipment_detail_id,
            te.location,
            te.incharge,
            te.equipment_setup_date,
            te.equipment_rehearsal_date
        FROM temp_equipment_details te
        JOIN equipment_list el ON te.equipment_name = el.equipment_name
        JOIN sub_category sc ON el.sub_category_id = sc.id
        LEFT JOIN (
            SELECT equipment_id, rental_price
            FROM stock_details
            WHERE (equipment_id, id) IN (
                SELECT equipment_id, MIN(id)
                FROM stock_details
                GROUP BY equipment_id
            )
        ) sd ON el.id = sd.equipment_id
        WHERE te.temp_id = %s
	ORDER BY te.equipment_detail_id
    '''

    print('Fetch the Equipment_Query', equipment_query)

    # Query to fetch connects details with billing or individual address based on client type
    connects_query = '''
        SELECT
            CASE
                WHEN company_name IS NOT NULL THEN 'Company'
                WHEN individual_name IS NOT NULL THEN 'Individual'
                ELSE NULL
            END AS match_type,
            billing_address,
            individual_address,
            country,
            state,
            city,
            post_code
        FROM connects
        WHERE company_name = %s OR individual_name = %s
        LIMIT 1
    '''
    print('Check the Connects Query:', connects_query)

    # Query to fetch company details from the `company_master` table
    company_query = '''
        SELECT name, gst_no, email, company_logo, address
        FROM company_master
    '''
    print('Fetch the Company Query:', company_query)

    with connection.cursor() as cursor:
        print('Inside the cursor connection')
        cursor.execute(job_query, [job_id])
        job = cursor.fetchone()
        print('Check the Job:', job)

        if not job:
            return JsonResponse({'error': 'Job not found'}, status=404)

        client_name = job[3]  # Extract client_name from the job
        print('Fetch the Client Name of Job:', client_name)

        cursor.execute(connects_query, [client_name, client_name])
        connects_details = cursor.fetchone()
        print('Fetch the connects Details:', connects_details)

        cursor.execute(company_query, [client_name])
        company_details = cursor.fetchone()
        print('Fetch the company Details:', company_details)

        cursor.execute(equipment_query, [job_id])
        equipment_details = cursor.fetchall()
        print('Fetch the equipment Details:', equipment_details)

        # Determine the match type and address to include
        match_type = connects_details[0] if connects_details else None
        billing_address = connects_details[1] if connects_details else None
        individual_address = connects_details[2] if connects_details else None
        country = connects_details[3] if connects_details else None
        state = connects_details[4] if connects_details else None
        city = connects_details[5] if connects_details else None
        post_code = connects_details[6] if connects_details else None
        print('This match type is working.')

        # Prepare job data with merged connects details
        job_data = {
            'id': job[0],
            'job_reference_no': job[1],
            'title': job[2],
            'client_name': job[3],
            'contact_person_name': job[4],
            'contact_person_number': job[5],
            'status': job[6],
            'venue_name': job[7],
            'venue_address': job[8],
            'notes': job[9] if job[9] is not None else "",
            'crew_type': job[10],
            'employee': job[11],
            'setup_date': job[12].strftime('%d-%m-%Y') if job[12] else None,
            'rehearsal_date': job[13].strftime('%d-%m-%Y') if job[13] else None,
            'event_date': job[14].strftime('%d-%m-%Y') if job[14] else None,
            'dismantle_date': job[15].strftime('%d-%m-%Y') if job[15] else None,
            'total_days': job[16],
            'amount_row': job[17],
            'discount': job[18],
            'amount_after_discount': job[19],
            'total_amount': job[20],
            'created_by': job[21],
            'created_date': job[22].strftime('%d-%m-%Y') if job[22] else None,
            'match_type': match_type,
            'address': billing_address if match_type == 'Company' else individual_address,
            'country': country,
            'state': state,
            'city': city,
            'post_code': post_code
        }
        print('Fetch the correct JOB DATA:', job_data)
        # Prepare company details if available
        company_data = {
            'company_name': company_details[0] if company_details else None,
            'gst_no': company_details[1] if company_details else None,
            'email': company_details[2] if company_details else None,
            'company_logo': company_details[3] if company_details else None,  # This is the Cloudinary image URL
            'address': company_details[4] if company_details else None
        } if company_details else None
        print('Fetch the company DATA:', company_data)

        # Initialize total rental sum and list for equipment data

    total_rental_sum = 0
    equipment_data = []
    print('Fetch the equipment DATA:', equipment_data)

    # Process each equipment detail
    for detail in equipment_details:
        print('Processing Equipment Details:', equipment_details)
        print('Processing Detail:', detail)

        rental_price = int(detail[6]) if detail[6] is not None else 0
        total_days_price = int(detail[1]) * rental_price if rental_price else 'Not Available'
        total_rental_price = int(detail[1]) * int(
            job_data['total_days']) * rental_price if rental_price else 'Not Available'

        if isinstance(total_rental_price, int):
            total_rental_sum += total_rental_price

            # Attempt to parse equipment_setup_date as a date
        setup_date = detail[11]
        if isinstance(setup_date, str):
            try:
                setup_date = datetime.strptime(setup_date, '%Y-%m-%d')  # Adjust format if needed
            except ValueError:
                setup_date = None  # Handle invalid date format gracefully

        # Attempt to parse equipment_rehearsal_date as a date
        rehearsal_date = detail[12]
        if isinstance(rehearsal_date, str):
            try:
                rehearsal_date = datetime.strptime(rehearsal_date, '%Y-%m-%d')  # Adjust format if needed
            except ValueError:
                rehearsal_date = None  # Handle invalid date format gracefully

        equipment_data.append({
            # 'temp_equipment_id': detail[0],
            'equipment_name': detail[0],
            'quantity': detail[1],
            'equipment_id': detail[2],
            'category_type': detail[3],
            'sub_category_id': detail[4],
            'sub_category_name': detail[5],
            'rental_price': rental_price if rental_price else 'Not Available',
            'equipment_notes': detail[7],
            'equipment_detail_id': detail[8],
            'location': detail[9],
            'incharge': detail[10],
            'equipment_setup_date': setup_date.strftime('%d-%m-%Y') if setup_date else 'Not Available',
            'equipment_rehearsal_date': rehearsal_date.strftime('%d-%m-%Y') if rehearsal_date else 'Not Available',
            'total_days_price': total_days_price,
            'total_rental_price': total_rental_price


        })

    print('Final Equipment Data:', equipment_data)

    # Fetch the discount and calculate the total after discount
    discount = float(job_data['discount']) if job_data['discount'] else 0
    print('Fetch the DISCOUNT:', discount)
    total_after_discount = total_rental_sum - (total_rental_sum * (discount / 100))
    print('Fetch the TOTAL AFTER DISCOUNT:', total_after_discount)

    # Add 18% GST to the total_after_discount
    gst_percentage = 18
    gst_amount = total_after_discount * (gst_percentage / 100)
    total_with_gst = total_after_discount + gst_amount
    # Prepare the final response data including the total sum of rental prices
    response_data = {
        'job': job_data,
        'company': company_data,
        'equipment_details': equipment_data,
        'total_days': job_data['total_days'],
        'total_rental_sum': total_rental_sum,  # Include the sum of all total_rental_price
        'discount': discount,  # The discount percentage
        'total_after_discount': total_after_discount,
        'gst_percentage': gst_percentage,  # GST percentage applied
        'gst_amount': gst_amount,  # GST amount
        'total_with_gst': total_with_gst  # Final total after applying GST
    }
    print('Fetch the response DATA:', response_data)

    return JsonResponse(response_data)

def fetch_crew_allocation_edit(request):
    print('Check the fetch crew allocation edit function')
    job_id = request.GET.get('jobId')  # Get jobId from the request
    print('Check the jobId of fetch crew allocation:', job_id)

    with connection.cursor() as cursor:
        print('Check the cursor connection..')
        # Query the temp_crew_allocation table based on jobId
        cursor.execute("""
            SELECT 
                tca.id,  -- Assuming crew_allocation_id exists in the table
                tca.crew_type, 
                COALESCE(e.name, '') AS employee_name,  -- Use COALESCE to handle NULL values 
                tca.crew_no_of_days, 
                tca.perday_charges, 
                tca.total, 
                tca.crew_notes
            FROM 
                public.temp_crew_allocation tca
            LEFT JOIN 
                public.employee e ON CAST(tca.emp_id AS integer) = e.id
            WHERE 
                tca.temp_id = %s
        """, [job_id])

        rows = cursor.fetchall()
        print('Check the rows of fetch crew allocation:', rows)

    # Prepare the response data
    crew_allocations = []
    print('check the crew allocation details working []', crew_allocations)
    for row in rows:
        crew_allocations.append({
            'crewId': row[0],
            'crewType': row[1],
            'employeeName': row[2] if row[2] else '',  # Set a default value if employee_name is empty
            'noOfDays': row[3],
            'perDayCharges': row[4],
            'total': row[5],
            'crewNotes': row[6],
        })
        print('Check the crew allocation:', crew_allocations)
        print('Check the row allocation:', row)
        print('Check the rows allocation:', rows)

    return JsonResponse(crew_allocations, safe=False)


def search_employee_crew(request):
    if request.method == 'GET':
        query = request.GET.get('query', '')

        if query:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT id, name FROM employee WHERE name ILIKE %s LIMIT 10", [f'%{query}%']
                )
                employees = cursor.fetchall()

            # Prepare the data to be sent as JSON
            employee_list = [{'id': emp[0], 'name': emp[1]} for emp in employees]
            return JsonResponse({'employees': employee_list})

        return JsonResponse({'employees': []})


def save_crew_delivery_allocation(request):
    if request.method == 'POST':
        temp_id = request.POST.get('temp_id')
        crew_type = request.POST.get('crew_type')
        employee_name = request.POST.get('employee_name')  # Changed to employee_name for clarity
        crew_no_of_days = request.POST.get('crew_no_of_days')
        perday_charges = request.POST.get('perday_charges')
        total = request.POST.get('total')
        crew_notes = request.POST.get('crew_notes')

        print('Check the form data:', temp_id, crew_type, employee_name, crew_no_of_days, perday_charges, total,
              crew_notes)

        # Call the PostgreSQL function
        call_function_query = """
        SELECT * FROM insert_temp_crew_delivery_allocation(%s, %s, %s, %s, %s, %s, %s);
        """

        with connection.cursor() as cursor:
            cursor.execute(call_function_query, [
                temp_id,
                crew_type,
                employee_name,  # Pass the employee name (as emp_id in the query)
                crew_no_of_days,
                perday_charges,
                total,
                crew_notes
            ])
            result = cursor.fetchone()
            print('Check the result of search employee crew:', result)

        if result:
            data = {
                'status': 'success',
                'crew_allocation_id': result[0],  # ID returned by the function
                'temp_id': result[1],
                'crew_type': result[2],
                'emp_name': result[3],  # Changed to emp_name to return the employee name
                'crew_no_of_days': result[4],
                'perday_charges': result[5],
                'total': result[6],
                'crew_notes': result[7]
            }
            print('fetch the data:', data)
            return JsonResponse(data)
        else:
            return JsonResponse({'status': 'error', 'message': 'Crew allocation not found'}, status=404)

    return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=400)


@csrf_exempt
def update_crew_allocation_delivery(request):
    print('check the update crew allcation delivery challen working.')
    if request.method == 'POST':
        print('check the post method is working.')
        # Retrieve data from the request
        crew_allocation_id = request.POST.get('id')
        crew_type = request.POST.get('crew_type')
        emp_id = request.POST.get('employee_name')
        no_of_days = request.POST.get('no_of_days')
        perday_charges = request.POST.get('perday_charges')
        total = request.POST.get('total')
        crew_notes = request.POST.get('crew_notes')
        print('check the form data:', crew_allocation_id, crew_type, emp_id, no_of_days, perday_charges, total, crew_notes)

        try:
            print('check the try block is working')
            # Call the PostgreSQL function to update the crew allocation
            with connection.cursor() as cursor:
                print('check the cursor connection object is working..')
                cursor.execute("""
                    SELECT manage_temp_crew_delivery(%s, %s, %s, %s, %s, %s, %s, %s);
                """, ['update', crew_allocation_id, crew_type, emp_id, no_of_days, perday_charges, total, crew_notes])
            print('Updated successfully..')
            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})

    return JsonResponse({'success': False, 'error': 'Invalid request method.'})
