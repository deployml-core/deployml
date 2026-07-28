import pandas as pd
from IPython.display import display, HTML


def display_services_table(df: pd.DataFrame):
    """Create a professional HTML table with clickable links"""
    html_content = """
    <div style="margin: 15px 0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;">
        <table style="border-collapse: collapse; width: 100%; border: 1px solid #ddd;">
            <thead>
                <tr style="background-color: #f8f9fa; border-bottom: 2px solid #dee2e6;">
                    <th style="padding: 12px; text-align: left; font-weight: 600; color: #495057;">Service</th>
                    <th style="padding: 12px; text-align: left; font-weight: 600; color: #495057;">URL</th>
                    <th style="padding: 12px; text-align: center; font-weight: 600; color: #495057;">Status</th>
                </tr>
            </thead>
            <tbody>
    """

    for _, row in df.iterrows():
        status_color = "#28a745" if row["Status"] == "Ready" else "#dc3545"
        status_bg = "#d4edda" if row["Status"] == "Ready" else "#f8d7da"

        html_content += f"""
            <tr style="border-bottom: 1px solid #dee2e6;">
                <td style="padding: 12px; font-weight: 500;">{row["Service"]}</td>
        """

        if row["URL"].startswith("http"):
            html_content += f'''
                <td style="padding: 12px;">
                    <a href="{row["URL"]}" target="_blank" 
                       style="color: #007bff; text-decoration: none; font-family: monospace; font-size: 0.9em;"
                       onmouseover="this.style.textDecoration='underline'"
                       onmouseout="this.style.textDecoration='none'">
                        {row["URL"]}
                    </a>
                </td>
            '''
        elif "PostgreSQL Database" in row["Service"] and row["Status"] == "Ready":
            # Style PostgreSQL connection info differently
            html_content += f"""
                <td style="padding: 12px; font-family: monospace; font-size: 0.9em; color: #495057; background-color: #f8f9fa;">
                    {row["URL"]}
                </td>
            """
        elif "Cron Job:" in row["Service"] and row["URL"].startswith(
            "https://console.cloud.google.com"
        ):
            # Style cron job links with special GCP console styling
            html_content += f'''
                <td style="padding: 12px;">
                    <a href="{row["URL"]}" target="_blank" 
                       style="color: #4285f4; text-decoration: none; font-family: monospace; font-size: 0.9em;"
                       onmouseover="this.style.textDecoration='underline'"
                       onmouseout="this.style.textDecoration='none'">
                        <span style="font-size: 0.8em; color: #666;">🔗 GCP Console:</span><br>
                        {row["URL"]}
                    </a>
                </td>
            '''
        else:
            html_content += f'<td style="padding: 12px; font-family: monospace; color: #6c757d;">{row["URL"]}</td>'

        html_content += f"""
                <td style="padding: 12px; text-align: center;">
                    <span style="background-color: {status_bg}; color: {status_color}; 
                                 padding: 4px 8px; border-radius: 4px; font-size: 0.85em; font-weight: 600;">
                        {row["Status"]}
                    </span>
                </td>
            </tr>
        """

    html_content += """
            </tbody>
        </table>
    </div>
    """

    try:
        display(HTML(html_content))
    except:
        # Fallback to simple print if HTML display fails
        for _, row in df.iterrows():
            status = "[READY]" if row["Status"] == "Ready" else "[MISSING]"
            print(f"{status:10} {row['Service']:35} {row['URL']}")
